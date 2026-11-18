FROM crm-local:final-navigation-9043bb5dc09a4abc9d562c7bcf2ef4d2

COPY --chown=frappe:frappe . /home/frappe/native-schedule
RUN --network=none env/bin/python -B /home/frappe/final-navigation/deploy/verify_final_navigation.py assets && \
    env/bin/python -B /home/frappe/native-schedule/deploy/native-schedule/verify.py before && \
    env/bin/python -B /home/frappe/native-schedule/frontend-patches/l3-scheduling/native/apply.py apps/crm --app-source /home/frappe/native-schedule/app-source/team_schedule --check && \
    env/bin/python -B /home/frappe/native-schedule/frontend-patches/l3-scheduling/native/apply.py apps/crm --app-source /home/frappe/native-schedule/app-source/team_schedule && \
    env/bin/python -B /home/frappe/native-schedule/deploy/native-schedule/verify.py legacy && \
    cp -a assets/. sites/assets/ && \
    bench build --app crm && \
    cp -a sites/assets/. assets/ && \
    env/bin/python -B /home/frappe/native-schedule/frontend-patches/l3-scheduling/native/apply.py apps/crm --app-source /home/frappe/native-schedule/app-source/team_schedule --verify && \
    env/bin/python -B /home/frappe/native-schedule/deploy/native-schedule/verify.py assets

ARG SCHEDULE_REVISION
ARG INTEGRATION_REVISION
LABEL crm.native-schedule.integration="native-schedule-s021-v1" \
      crm.native-schedule.base="sha256:c2601699d018675f1e2fc87a13c7fa4963090182eccfc70a8e51ed5ccdfbe062" \
      crm.native-schedule.revision="${SCHEDULE_REVISION}" \
      crm.native-schedule.integration.revision="${INTEGRATION_REVISION}"
