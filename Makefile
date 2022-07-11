DOCKER_PREFIX=mkorpershoek
DOCKER_DEV_PREFIX=localhost:5000/mkorpershoek
DOCKER_NAME=repo-resource
DOCKER_DEV_NAME=testing-repo-resource

all: docker

docker:
	docker build . \
		--tag "$(DOCKER_NAME):latest"

dev-docker: docker
	docker build . -f Dockerfile.development \
		--tag "$(DOCKER_DEV_NAME):latest"

test: dev-docker
	docker run $(DOCKER_DEV_NAME)

push: docker
		docker image tag ${DOCKER_NAME} ${DOCKER_PREFIX}/${DOCKER_NAME}
		docker push ${DOCKER_PREFIX}/${DOCKER_NAME}

dev-push: docker
		docker image tag ${DOCKER_NAME} ${DOCKER_DEV_PREFIX}/${DOCKER_NAME}
		docker push ${DOCKER_DEV_PREFIX}/${DOCKER_NAME}
