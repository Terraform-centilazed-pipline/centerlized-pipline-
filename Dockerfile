# Multi-stage build for lightweight Terraform + OPA + Python image
FROM alpine:3.19 AS builder

# Install build dependencies
RUN apk add --no-cache \
    curl \
    unzip \
    wget

# Download and install Terraform
ARG TERRAFORM_VERSION=1.11.0
RUN curl -fsSL https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip -o terraform.zip && \
    unzip terraform.zip && \
    chmod +x terraform

# Download and install OPA
ARG OPA_VERSION=0.59.0
RUN curl -fsSL https://openpolicyagent.org/downloads/v${OPA_VERSION}/opa_linux_amd64_static -o opa && \
    chmod +x opa

# Final lightweight image
FROM alpine:3.19

# Install runtime dependencies only
RUN apk add --no-cache \
    bash \
    git \
    jq \
    python3 \
    py3-pip \
    py3-setuptools \
    py3-wheel \
    curl \
    ca-certificates \
    && rm -rf /var/cache/apk/*

# Install Python packages
RUN pip3 install --no-cache-dir \
    pyyaml \
    requests \
    boto3

# Copy binaries from builder stage
COPY --from=builder /terraform /usr/local/bin/terraform
COPY --from=builder /opa /usr/local/bin/opa

# Create non-root user for security
RUN adduser -D -s /bin/bash runner

# Set working directory
WORKDIR /workspace

# Set user
USER runner

# Verify installations
RUN terraform --version && \
    opa version && \
    python3 --version && \
    jq --version

# Set default entrypoint
ENTRYPOINT ["/bin/bash"]