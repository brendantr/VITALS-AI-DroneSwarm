# Docker Setup and Usage Guide

## Prerequisites

Before you begin, make sure you have Docker installed on your system:
- **Windows**: [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
- **macOS**: [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)
- **Linux**: [Docker Engine](https://docs.docker.com/engine/install/)

## Building the Docker Image Locally

### Step 1: Navigate to the App Directory

Open your terminal/command prompt and navigate to the app directory:

```bash
# Windows (PowerShell/Command Prompt)
cd "C:\path\to\VITALS-AI-DroneSwarm\app"

# macOS/Linux
cd /path/to/VITALS-AI-DroneSwarm/app
```

### Step 2: Verify Files are Present

Make sure you're in the correct directory by checking for required files:

```bash
# Should show Dockerfile, requirements.txt, startup.py, and other files
ls
# or on Windows:
dir
```

### Step 3: Build the Docker Image

Build the Docker image with the following command:

```bash
docker build -t vitals-web-app .
```

**Note**: The `.` at the end is important - it tells Docker to use the current directory as the build context.

#### Build Options

For different platforms (useful for deployment):
```bash
docker build -t vitals-web-app .

# 
```

## Running the Docker Container

### Basic Run Command

```bash
docker run vitals-web-app
```

This will:
1. Print "Hello world"
2. List all installed Python packages
3. Exit when complete

## Troubleshooting

### Common Issues and Solutions

#### 1. "no such file or directory" Error
```
ERROR: failed to solve: failed to read dockerfile: open Dockerfile: no such file or directory
```
**Solution**: Make sure you're in the correct directory (`app` folder) where the Dockerfile is located.

#### 2. Permission Denied Errors
**Windows**: Make sure Docker Desktop is running and you have administrator privileges.
**Linux**: You might need to run commands with `sudo` or add your user to the docker group.

#### 3. Build Context Too Large
If you get warnings about large build context:
```bash
# Make sure .dockerignore is present and properly configured
cat .dockerignore
```

#### 4. Platform Architecture Warnings
If you see platform warnings, specify the platform explicitly:
```bash
docker build --platform=linux/amd64 -t vitals-web-app .
```

## Container Management

### View Running Containers
```bash
docker ps
```

### View All Containers (including stopped)
```bash
docker ps -a
```

### Stop a Running Container
```bash
docker stop vitals-container
```

### Remove a Container
```bash
docker rm vitals-container
```

### Remove the Image
```bash
docker rmi vitals-web-app
```

### View Container Logs
```bash
docker logs vitals-container
```

## Development Workflow

### Rebuilding After Changes

When you make changes to the code or Dockerfile:

1. **Stop any running containers**:
   ```bash
   docker stop vitals-container
   docker rm vitals-container
   ```

2. **Rebuild the image**:
   ```bash
   docker build -t vitals-web-app .
   ```

3. **Run the new container**:
   ```bash
   docker run vitals-web-app
   ```

### Quick Rebuild and Run
```bash
docker build -t vitals-web-app . && docker run vitals-web-app
```

## Deploying your application to the cloud

### Deploying to Cloud Platforms

#### Step 1: Build for Target Platform
First, build your image for the target platform:
```bash
# For most cloud providers (AMD64)
docker build --platform=linux/amd64 -t vitals-web-app .
```

#### Step 2: Tag for Registry
Tag your image for your container registry:
```bash
# For Docker Hub
docker tag vitals-web-app yourusername/vitals-web-app:latest

# For AWS ECR
docker tag vitals-web-app 123456789012.dkr.ecr.us-west-2.amazonaws.com/vitals-web-app:latest

# For Google Container Registry
docker tag vitals-web-app gcr.io/your-project-id/vitals-web-app:latest
```

#### Step 3: Push to Registry
Push your image to the container registry:
```bash
# Docker Hub
docker push yourusername/vitals-web-app:latest

# AWS ECR (after authentication)
docker push 123456789012.dkr.ecr.us-west-2.amazonaws.com/vitals-web-app:latest

# Google Container Registry (after authentication)
docker push gcr.io/your-project-id/vitals-web-app:latest
```

#### Step 4: Deploy
Deploy using your cloud provider's container service (ECS, Cloud Run, etc.).

## References and Additional Resources

### Docker Documentation
* [Docker's Python guide](https://docs.docker.com/language/python/)
* [Docker getting started](https://docs.docker.com/go/get-started-sharing/)
* [Dockerfile best practices](https://docs.docker.com/develop/dev-best-practices/)
* [Docker Compose documentation](https://docs.docker.com/compose/)

### Project-Specific Information
* See the main project README for application-specific details
* Check `requirements.txt` for Python dependencies
* Review `startup.py` for the container entry point logic

### Support
If you encounter issues not covered in this guide:
1. Check the Docker logs: `docker logs [container-name]`
2. Verify your Docker installation: `docker --version`
3. Ensure all required files are present in the build context
4. Review the Dockerfile for any recent changes