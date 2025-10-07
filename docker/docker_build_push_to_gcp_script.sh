PROJECT_ID=your-project
REGION=us-central1
REPO=qcraft
IMAGE=qcraft-gpu:latest

gcloud auth configure-docker ${REGION}-docker.pkg.dev
docker build -f docker/Dockerfile.gpu -t ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE} .
docker push ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE}