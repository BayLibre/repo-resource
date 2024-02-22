# Repo resource

Track changes in a [repo](https://gerrit.googlesource.com/git-repo/+/master/#repo) project.

## Source configuration

* `url`: *Required.* manifest repository location.

* `revision`: *Optional.* manifest branch or revision (use `HEAD` for default).

* `name`: *Optional.* initial manifest file. (use `default.xml` for default).

* `private_key`: *Optional.* Private key to use when pulling/pushing.
    Should be newline (`\n`) terminated.
    Note that keys requiring a passphrase are un-supported.
    Example:

    ```yaml
    private_key: |
      -----BEGIN RSA PRIVATE KEY-----
      MIIEowIBAAKCAQEAtCS10/f7W7lkQaSgD/mVeaSOvSF9ql4hf/zfMwfVGgHWjj+W
      <Lots more text>
      DWiJL+OFeg9kawcUL6hQ8JeXPhlImG6RTUffma9+iGQyyBMCGd1l
      -----END RSA PRIVATE KEY-----
    ```

* `depth`: *Optional.* shallow clone with a history truncated to the specified number of commits.
    Defaults to full git clone for each project.

* `jobs`: *Optional.* number of jobs to run in parallel (default: 0; based on number of CPU cores)
   Reduce this if you observe network errors.

* `check_jobs`: for check step only: number of jobs to run in parallel (default: jobs\*2,
  2 if jobs is undefined).

### Example

Resource configuration for a public project using repo (Android)

```yaml
resource_types:
- name: repo
  type: registry-image
  source:
    repository: mkorpershoek/repo-resource
    tag: v1.0.0

resources:
- name: aosp
  type: repo
  check_every: 2h # default of 1min seems too frequent
  source:
    url: https://android.googlesource.com/platform/manifest
    branch: master
    name: default.xml
    depth: 1 # use shallow clone for faster syncing
    jobs: 4  # run with -j4
```

## Behavior

### `check`: Check for new versions in each project under a manifest

Repo init and repo sync are called for a given manifest.
After that, `--revision-as-HEAD` is called to capture the HEADs of each each project.
The whole list of projects is returned as a "manifest version".

### `in`: Syncs the repository, for a given manifest version

Repo syncs the repo to the destination, and locks it down to a given manifest
version.
It will return the same given ref as version.

### `out`: No-op

Out is not implemented.


## Contributing/development

### Rebuilding the docker image

```
make
```

### Publish to docker hub

```
make push
```

### Unit testing

Use `make test` for running the unit(integration) tests:
```
make test
```

If you wish to run a single test, just edit the `Dockerfile.development`:

```diff
diff --git a/Dockerfile.development b/Dockerfile.development
index 81fbb349c014..431f07b59917 100644
--- a/Dockerfile.development
+++ b/Dockerfile.development
@@ -4,4 +4,4 @@ FROM repo-resource:latest
 COPY repo_resource /root/repo_resource
 COPY development/ssh/ /root/development/ssh/
 WORKDIR /root/
-CMD python -m unittest
+CMD python -m unittest repo_resource.test_check.TestCheck.test_branch_defaults_to_HEAD
```

### Local concourse instance and docker registry.

It's also possible to use a local docker registry (instead of docker hub) for development.
This allows closer "end-to-end" testing on a development workstation.

This section assumes that you've installed `docker` and `docker-compose` as documented in
https://concourse-ci.org/getting-started.html

1. Start by running a concourse development instance and install `fly`:
   ```
   curl -O https://concourse-ci.org/docker-compose.yml
   docker-compose up -d

   curl 'http://localhost:8080/api/v1/cli?arch=amd64&platform=linux' -o fly \
       && chmod +x ./fly && mv ./fly /usr/local/bin/

   fly -t tutorial login -c http://localhost:8080 -u test -p test
   ```
   See https://concourse-ci.org/quick-start.html#docker-compose-concourse for details

2. Start your local docker registry:
   ```
   # retrieve the concourse container's network name
   container_name=$(docker ps --filter 'ancestor=concourse/concourse' --format "{{.Names}}")
   network_name=$(docker container inspect $name -f "{{.HostConfig.NetworkMode}}" $container_name)
   docker run --network ${network_name} -d -p 5000:5000 --name registry registry:2
   ```
   See https://www.docker.com/blog/how-to-use-your-own-registry-2/ for more information

3. Rebuild and publish your docker image to the local registry:
   ```
   make dev-push
   ```

4. Get the IP address of your `registry` container. This is needed because the `concourse/concourse`
   container seems unable to lookup by hostname address:
   ```
   registry_container_id=$(docker ps --no-trunc --filter "name=registry" --format="{{.ID}}")
   docker inspect --format='{{range .NetworkSettings.Networks}}{{println .IPAddress}}{{end}}' ${registry_container_id}
   ```

   Note the IP address (`172.20.0.4` in this example).

5. Publish a development job with `fly` using the [development `pipeline.yml`](./development/pipeline.yml)
   ```
   fly -t tutorial set-pipeline -p development -c development/pipeline.yml
   fly -t tutorial unpause-pipeline -p development
   fly -t tutorial check-resource -r development/aosp-tools
   ```

   Note: eventually, you'll have to patch `development/pipeline.yml` with the IP address from step 4.
