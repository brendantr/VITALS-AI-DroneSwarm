"""Mock-only endpoint tests; also runnable directly with standard-library unittest."""

import ast
import importlib.util
from pathlib import Path
from types import ModuleType
import unittest
from unittest.mock import Mock, call, patch


APP_DIR = Path(__file__).resolve().parents[1]
SITL_ENDPOINT = "tcp:127.0.0.1:14550"
NETWORK_TARGETS = [
    "tcp:127.0.0.1:14450",
    SITL_ENDPOINT,
    "udp:127.0.0.1:14445",
    "udp:127.0.0.1:14550",
]
CONNECTION_OPTIONS = {"autoreconnect": False, "mavlink_version": "2.0"}


class DispatcherConnectionTests(unittest.TestCase):
    def setUp(self):
        # Load the real Dispatcher without requiring pymavlink or starting its
        # constructor's background thread. Every connection factory is mocked.
        pymavlink = ModuleType("pymavlink")
        pymavlink.mavutil = Mock()
        spec = importlib.util.spec_from_file_location(
            "_dispatcher_connection_test", APP_DIR / "Dispatcher" / "Dispatcher.py"
        )
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"pymavlink": pymavlink}):
            spec.loader.exec_module(self.module)
        self.dispatcher = self.module.Dispatcher.__new__(self.module.Dispatcher)
        self.dispatcher.master = None
        self.dispatcher.connected_system_id = None
        self.dispatcher.connected_component_id = None
        self.factory = self.module.mavutil.mavlink_connection
        self.platform = self.enter_patch(patch.object(self.module.platform, "system"))
        self.glob = self.enter_patch(patch.object(self.module.glob, "glob"))

    def enter_patch(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def assert_disconnected(self):
        self.assertIsNone(self.dispatcher.master)
        self.assertIsNone(self.dispatcher.connected_system_id)
        self.assertIsNone(self.dispatcher.connected_component_id)

    def test_explicit_network_target_only_without_discovery_or_serial_baud(self):
        self.platform.side_effect = AssertionError("Explicit mode must not discover")
        self.glob.side_effect = AssertionError("Explicit mode must not discover")
        for target in (SITL_ENDPOINT, "udp:127.0.0.1:14550"):
            for baud in (None, 115200):
                with self.subTest(target=target, baud=baud):
                    self.factory.reset_mock()
                    self.factory.return_value = Mock()
                    self.assertTrue(self.dispatcher.connect(target, baud=baud))
                    self.factory.assert_called_once_with(target, **CONNECTION_OPTIONS)
        self.platform.assert_not_called()
        self.glob.assert_not_called()

    def test_explicit_factory_failure_has_no_fallback(self):
        self.factory.side_effect = OSError("Connection refused")
        self.assertFalse(self.dispatcher.connect(SITL_ENDPOINT))
        self.factory.assert_called_once_with(SITL_ENDPOINT, **CONNECTION_OPTIONS)
        self.platform.assert_not_called()
        self.glob.assert_not_called()
        self.assert_disconnected()

    def test_explicit_factory_failure_clears_stale_state_without_closing_stale_master(self):
        stale_master = Mock()
        self.dispatcher.master = stale_master
        self.dispatcher.connected_system_id = 99
        self.dispatcher.connected_component_id = 100
        state_at_factory = []

        def fail_factory(*args, **kwargs):
            state_at_factory.append((
                self.dispatcher.master,
                self.dispatcher.connected_system_id,
                self.dispatcher.connected_component_id,
            ))
            raise OSError("Connection refused")

        self.factory.side_effect = fail_factory
        self.assertFalse(self.dispatcher.connect(SITL_ENDPOINT))
        self.factory.assert_called_once_with(SITL_ENDPOINT, **CONNECTION_OPTIONS)
        self.platform.assert_not_called()
        self.glob.assert_not_called()
        self.assertEqual(state_at_factory, [(None, None, None)])
        self.assert_disconnected()
        stale_master.close.assert_not_called()

    def test_failed_handles_are_closed_and_disconnected_without_fallback(self):
        for failure in ("heartbeat_missing", "heartbeat_exception", "source_exception"):
            with self.subTest(failure=failure):
                master = Mock()
                if failure == "heartbeat_missing":
                    master.wait_heartbeat.return_value = None
                elif failure == "heartbeat_exception":
                    master.wait_heartbeat.side_effect = RuntimeError("Heartbeat failed")
                else:
                    heartbeat = master.wait_heartbeat.return_value
                    heartbeat.get_srcSystem.return_value = 1
                    heartbeat.get_srcComponent.side_effect = RuntimeError("Invalid source")
                self.factory.reset_mock()
                self.factory.return_value = master
                self.dispatcher.connected_system_id = 99
                self.dispatcher.connected_component_id = 99

                self.assertFalse(self.dispatcher.connect(SITL_ENDPOINT))

                self.factory.assert_called_once_with(SITL_ENDPOINT, **CONNECTION_OPTIONS)
                master.close.assert_called_once_with()
                self.assert_disconnected()
        self.platform.assert_not_called()
        self.glob.assert_not_called()

    def test_close_exception_still_clears_failed_connection(self):
        master = Mock()
        master.wait_heartbeat.return_value = None
        master.close.side_effect = OSError("Close failed")
        self.factory.return_value = master
        self.assertFalse(self.dispatcher.connect(SITL_ENDPOINT))
        self.factory.assert_called_once_with(SITL_ENDPOINT, **CONNECTION_OPTIONS)
        master.close.assert_called_once_with()
        self.assert_disconnected()

    def test_explicit_serial_baud_and_default(self):
        for target in ("COM10", "/dev/cu.usbserial-test"):
            for baud, expected_baud in ((115200, 115200), (None, 57600)):
                with self.subTest(target=target, baud=baud):
                    self.factory.reset_mock()
                    self.factory.return_value = Mock()
                    self.assertTrue(self.dispatcher.connect(target, baud=baud))
                    self.factory.assert_called_once_with(
                        target, baud=expected_baud, **CONNECTION_OPTIONS
                    )
        self.platform.assert_not_called()
        self.glob.assert_not_called()

    def assert_legacy_attempts(self, targets):
        # Both no-argument discovery and a baud without a target retain legacy
        # serial settings. Missing heartbeats let us observe every candidate.
        for options in ({}, {"baud": 115200}):
            with self.subTest(options=options):
                masters = [Mock() for _ in targets]
                for master in masters:
                    master.wait_heartbeat.return_value = None
                self.factory.reset_mock()
                self.factory.side_effect = masters
                self.assertFalse(self.dispatcher.connect(**options))
                expected = [
                    call(target, baud=57600, **CONNECTION_OPTIONS)
                    if target.startswith("COM") or target.startswith("/dev/")
                    else call(target, **CONNECTION_OPTIONS)
                    for target in targets
                ]
                self.assertEqual(self.factory.call_args_list, expected)
                for master in masters:
                    master.close.assert_called_once_with()
                self.assert_disconnected()

    def test_legacy_windows_candidate_order_and_baud(self):
        self.platform.return_value = "Windows"
        self.assert_legacy_attempts(["COM10"] + NETWORK_TARGETS)
        self.glob.assert_not_called()

    def test_legacy_non_windows_candidate_order_and_baud(self):
        self.platform.return_value = "Darwin"
        serial_groups = {
            "/dev/cu.usbserial*": ["/dev/cu.usbserial-z", "/dev/cu.usbserial-a"],
            "/dev/tty.usbserial*": ["/dev/tty.usbserial-z", "/dev/tty.usbserial-a"],
            "/dev/cu.usbmodem*": ["/dev/cu.usbmodem-z", "/dev/cu.usbmodem-a"],
            "/dev/tty.usbmodem*": ["/dev/tty.usbmodem-z", "/dev/tty.usbmodem-a"],
        }
        self.glob.side_effect = serial_groups.__getitem__
        targets = [
            "/dev/cu.usbserial-a", "/dev/cu.usbserial-z",
            "/dev/tty.usbserial-a", "/dev/tty.usbserial-z",
            "/dev/cu.usbmodem-a", "/dev/cu.usbmodem-z",
            "/dev/tty.usbmodem-a", "/dev/tty.usbmodem-z",
        ] + NETWORK_TARGETS
        self.assert_legacy_attempts(targets)
        self.assertEqual(
            self.glob.call_args_list,
            [call(pattern) for pattern in serial_groups] * 2,
        )


class EndpointForwardingTests(unittest.TestCase):
    def test_mission_state_endpoint_baud_forwarding_and_default_call_static(self):
        # Read syntax only: never import, compile, instantiate, or execute any
        # missionState code, including its constructor and connection method.
        tree = ast.parse((APP_DIR / "missionState.py").read_text())
        state_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "missionState"
        )
        methods = {
            node.name: node for node in state_class.body
            if isinstance(node, ast.FunctionDef)
        }
        constructor = methods["__init__"]
        defaults = {
            arg.arg: ast.literal_eval(value)
            for arg, value in zip(
                constructor.args.args[-len(constructor.args.defaults):],
                constructor.args.defaults,
            )
        }
        self.assertIsNone(defaults["mavlink_endpoint"])
        self.assertIsNone(defaults["mavlink_baud"])
        assignments = [ast.dump(node) for node in constructor.body if isinstance(node, ast.Assign)]
        for statement in (
            "self.mavlink_endpoint = mavlink_endpoint",
            "self.mavlink_baud = mavlink_baud",
        ):
            self.assertIn(ast.dump(ast.parse(statement).body[0]), assignments)

        expected = ast.parse(
            "if self.mavlink_endpoint is None:\n"
            "    success = self.dispatcher.connect()\n"
            "elif self.mavlink_baud is None:\n"
            "    success = self.dispatcher.connect(connection_string=self.mavlink_endpoint)\n"
            "else:\n"
            "    success = self.dispatcher.connect(\n"
            "        connection_string=self.mavlink_endpoint, baud=self.mavlink_baud)\n"
        ).body[0]
        branches = [ast.dump(node) for node in methods["connect_to_mavlink"].body if isinstance(node, ast.If)]
        self.assertIn(ast.dump(expected), branches)

    def test_run_sim_sets_local_endpoint_without_baud_or_launching_gui(self):
        tree = ast.parse((APP_DIR / "run_sim.py").read_text())
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "missionState"
        ]
        self.assertEqual(len(calls), 1)
        keywords = {item.arg: ast.literal_eval(item.value) for item in calls[0].keywords}
        self.assertEqual(keywords, {"sim_only": True, "mavlink_endpoint": SITL_ENDPOINT})


if __name__ == "__main__":
    unittest.main()
