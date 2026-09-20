import { cp, mkdir, rm } from "node:fs/promises";

const destination = new URL("../../backend/app/static/", import.meta.url);
await rm(destination, { recursive: true, force: true });
await mkdir(destination, { recursive: true });
await cp(new URL("../out/", import.meta.url), destination, { recursive: true });
