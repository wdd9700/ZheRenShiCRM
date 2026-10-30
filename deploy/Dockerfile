FROM ghcr.io/frappe/crm@sha256:c3873edce03a0e9327306092c5f392b182304d905f9286057f90fb5739f810ca

USER frappe
WORKDIR /home/frappe/frappe-bench
RUN printf '{}\n' > sites/common_site_config.json && \
    bench get-app --branch v1.90.0 --skip-assets https://github.com/frappe/crm && \
    test "$(git -C apps/crm rev-parse HEAD)" = "36bd8859f2a6345a620477bc708d0546e8c3f08a" && \
    git -C apps/crm diff --exit-code -- yarn.lock frontend/yarn.lock
RUN --network=none bench build --app crm && \
    cp -a sites/assets/. assets/ && \
    env/bin/python -c "import crm; print(crm.__version__)" && \
    bench version

COPY --chown=frappe:frappe apps/resource_import apps/resource_import
RUN env/bin/pip install --no-deps --no-build-isolation -e apps/resource_import && \
    env/bin/python -c "import resource_import; print(resource_import.__version__)" && \
    printf 'frappe\ncrm\nresource_import\n' > sites/apps.txt

LABEL org.opencontainers.image.source="https://github.com/frappe/crm" \
      org.opencontainers.image.revision="36bd8859f2a6345a620477bc708d0546e8c3f08a" \
      org.opencontainers.image.version="1.90.0-resource-import-0.1.0"
