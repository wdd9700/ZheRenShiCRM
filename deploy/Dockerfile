FROM ghcr.io/frappe/crm@sha256:c3873edce03a0e9327306092c5f392b182304d905f9286057f90fb5739f810ca

USER frappe
WORKDIR /home/frappe/frappe-bench
RUN printf '{}\n' > sites/common_site_config.json && \
    bench get-app --branch v1.90.0 --skip-assets https://github.com/frappe/crm && \
    test "$(git -C apps/crm rev-parse HEAD)" = "36bd8859f2a6345a620477bc708d0546e8c3f08a" && \
    git -C apps/crm diff --exit-code -- yarn.lock frontend/yarn.lock
RUN --network=none mkdir -p sites/assets && \
    cp -a assets/. sites/assets/ && \
    bench build --app crm && \
    env/bin/python -c "import json; from pathlib import Path; old=json.loads(Path('assets/assets.json').read_text()); new=json.loads(Path('sites/assets/assets.json').read_text()); required=('frappe-web.bundle.js','website.bundle.css','login.bundle.css','desk.bundle.js'); assert all(key in old for key in required), 'Base Framework asset manifest is incomplete'; assert all(new.get(key)==value for key,value in old.items()), 'Framework asset mappings were lost'; assert all(value.startswith('/assets/') and (Path('sites')/value.lstrip('/')).is_file() for value in new.values()), 'Mapped asset file is missing'" && \
    cp -a sites/assets/. assets/ && \
    env/bin/python -c "import crm; print(crm.__version__)" && \
    bench version

COPY --chown=frappe:frappe apps/resource_import apps/resource_import
RUN env/bin/pip install --no-deps --no-build-isolation -e apps/resource_import && \
    env/bin/python -c "import resource_import; print(resource_import.__version__)" && \
    printf 'frappe\ncrm\nresource_import\n' > sites/apps.txt

COPY --chown=frappe:frappe apps/team_access apps/team_access
RUN env/bin/pip install --no-deps -e apps/team_access && \
    printf 'frappe\ncrm\nresource_import\nteam_access\n' > sites/apps.txt
RUN --network=none bench build --app team_access && \
    cp -a sites/assets/. assets/ && \
    env/bin/python -c "import crm, resource_import, team_access; print(crm.__version__, resource_import.__version__, team_access.__version__)" && \
    test -s apps/team_access/team_access/public/access.js && \
    test -s apps/team_access/team_access/public/page.js && \
    bench version

ARG RESOURCE_IMPORT_REVISION=working-tree
ARG TEAM_ACCESS_REVISION=working-tree
LABEL org.opencontainers.image.source="https://github.com/frappe/crm" \
      org.opencontainers.image.revision="36bd8859f2a6345a620477bc708d0546e8c3f08a" \
      org.opencontainers.image.version="1.90.0-team-access-0.1.0" \
      crm.resource-import.revision="${RESOURCE_IMPORT_REVISION}" \
      crm.team-access.revision="${TEAM_ACCESS_REVISION}"
