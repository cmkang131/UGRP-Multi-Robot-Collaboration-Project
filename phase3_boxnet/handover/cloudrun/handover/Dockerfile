FROM us-docker.pkg.dev/<project-id>/ugrp/ugrp-run@sha256:6599cdc46e1dc6b89881466279b9360ba4b2baf8853b2f2f89cce0256ee5ad26
ARG RUNTIME_HOME=/opt/runtime

USER root
WORKDIR /opt/ugrp
COPY exec/ ${RUNTIME_HOME}/hybrid/student-p2/
COPY handover/ ./handover/
COPY worker.py check_image.py layer.json ./
RUN ln -s ${RUNTIME_HOME}/hybrid/student-p2 exec \
 && mkdir -p handover/runtime \
 && ln -s ${RUNTIME_HOME}/hybrid/gseg-actor handover/runtime/act

ENV HANDOVER_ACT_MODEL=${RUNTIME_HOME}/hybrid/gseg-actor \
    HANDOVER_SCENE_ROOT=${RUNTIME_HOME}/hybrid/graw/scene/frozen_slim \
    PYTHONPATH=${RUNTIME_HOME}/hybrid/graw/pyvendor \
    MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
ARG RUNTIME_USER=1000
USER ${RUNTIME_USER}
RUN ${RUNTIME_HOME}/ugrp-cpu/bin/python -B /opt/ugrp/check_image.py
ENV PATH="${RUNTIME_HOME}/ugrp-cpu/bin:${PATH}"
ENTRYPOINT ["python", "-B", "/opt/ugrp/worker.py"]
