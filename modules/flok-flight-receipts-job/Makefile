version=1.1.1
docker-user=jaredhanson11
name=${docker-user}/flok-flight-receipts-job

build:
	docker build . --build-arg PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL} -t ${name}:${version}
push: build
	docker push ${name}:${version}