# 0007. Photos re-encoded and stored in S3

## Context
Photos live on a Docker volume (not shared between replicas), keep their EXIF
(GPS), and listings may reference images from any host.

## Decision
`POST /uploads` accepts one image, decodes it with Pillow (refusing anything
that is not a real JPEG/PNG/WebP, and decompression bombs), strips all
metadata, re-encodes to WebP at a bounded size, and stores it in S3 under its
content hash. It is served from CloudFront with a year's immutable caching.
Listings may only reference our own media.

## Rejected
- *Presigned direct-to-S3 uploads.* Faster, but the bytes are never inspected
  or re-encoded; would need an asynchronous processing pipeline. Worth it once
  upload volume justifies it.
