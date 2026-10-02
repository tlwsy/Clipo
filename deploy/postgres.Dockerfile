# Keep Alpine/PostgreSQL 16 so existing Compose volumes retain their locale/runtime family.
FROM postgres:16-alpine AS vector-build
RUN apk add --no-cache build-base curl \
    && curl -fsSL https://codeload.github.com/pgvector/pgvector/tar.gz/refs/tags/v0.8.2 -o /tmp/vector.tar.gz \
    && echo '69f4019389af05dc1c9548deb8628e62878e6e207c03907f2b8af2016472cdaa  /tmp/vector.tar.gz' | sha256sum -c - \
    && tar -xzf /tmp/vector.tar.gz -C /tmp \
    && cd /tmp/pgvector-0.8.2 \
    && make OPTFLAGS="" with_llvm=no \
    && make install with_llvm=no

FROM postgres:16-alpine
COPY --from=vector-build /usr/local/lib/postgresql/vector.so /usr/local/lib/postgresql/vector.so
COPY --from=vector-build /usr/local/share/postgresql/extension/vector* /usr/local/share/postgresql/extension/
