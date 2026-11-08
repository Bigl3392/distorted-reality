# G4 unresolved: supply BASE_IMAGE from the reviewed lock, pinned to a real digest.
# An absent argument fails the build. Do not build until G4 is resolved.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ENV PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1
COPY harness/run.py /harness/run.py
RUN chmod 0555 /harness/run.py
USER 65534:65534
WORKDIR /tmp
ENTRYPOINT []
CMD ["/harness/run.py"]
