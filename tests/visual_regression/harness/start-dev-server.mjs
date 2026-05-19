#!/usr/bin/env node
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createServer } from "vite";

const urlFile = process.argv[2];
if (!urlFile) {
	console.error("usage: start-dev-server.mjs <url-file>");
	process.exit(2);
}

const configFile = fileURLToPath(new URL("./vite.config.ts", import.meta.url));
const server = await createServer({
	configFile,
	server: {
		host: "127.0.0.1",
		port: 0,
		strictPort: false,
	},
});

await server.listen();
const url = server.resolvedUrls?.local[0];
if (!url) {
	console.error("vite did not report a local URL");
	process.exit(1);
}
writeFileSync(urlFile, url, "utf8");
console.log(`visual-regression harness listening on ${url}`);

let closing = false;
async function close() {
	if (closing) return;
	closing = true;
	await server.close();
	process.exit(0);
}

process.on("SIGINT", () => void close());
process.on("SIGTERM", () => void close());
setInterval(() => undefined, 60_000);
