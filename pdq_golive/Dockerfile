# PDQ testing to go live: PDQ alone, read-only, on the live index. Nothing from production.
# Built by .github/workflows/golive-image.yml from the repo root:
#   docker build -f pdq_golive/Dockerfile .
FROM python:3.12-slim

ARG GIT_SHA=unknown
ENV GOLIVE_IMAGE_SHA=${GIT_SHA} \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg libs for OpenCV's video reader, sshd for driving the run, curl for the self-stop
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-server curl ca-certificates procps \
        sysstat libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/* \
 && sed -i 's/#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config \
 && sed -i 's/#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config

# The same Python and library versions the laptop golden run used (5 Nov 2026). pdqhash may
# build from source, so a compiler is installed for this step and removed after it.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
 && pip install numpy==1.26.4 faiss-cpu==1.12.0 pdqhash==0.2.8 \
        opencv-python-headless==4.10.0.84 boto3==1.42.38 imageio-ffmpeg==0.5.1 \
 && apt-get purge -y build-essential && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pdq_golive/ /app/pdq_golive/
RUN cd /app/pdq_golive/vendor && sha256sum -c SHA256SUMS \
 && chmod +x /app/pdq_golive/boot.sh \
 && python3 -c "import faiss, pdqhash, cv2, numpy; print('libs ok', faiss.__version__, cv2.__version__)"

EXPOSE 22
ENTRYPOINT ["bash", "/app/pdq_golive/boot.sh"]
