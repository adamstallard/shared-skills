#!/bin/sh
cd "$(dirname "$0")" && ./node_modules/.bin/esbuild src/run.tsx --bundle --platform=node --format=esm --outfile=out/run.mjs --alias:claude-code=./src/shim.ts --jsx-factory=h --jsx-fragment=Fragment --log-level=warning --external:ink --external:react
