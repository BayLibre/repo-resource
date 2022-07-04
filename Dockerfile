FROM python:3
RUN git config --global user.email repo-resource@concourse-ci.org && \
    git config --global user.name repo-resource && \
    git config --global color.ui never

COPY ssh_config /root/.ssh/config

COPY repo_resource/requirements.txt /opt/resource/requirements.txt
RUN pip install -r opt/resource/requirements.txt
COPY repo_resource/check.py /opt/resource/check
COPY repo_resource/in_.py /opt/resource/in
COPY repo_resource/out.py /opt/resource/out
RUN chmod +x /opt/resource/*