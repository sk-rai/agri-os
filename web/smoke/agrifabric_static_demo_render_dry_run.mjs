import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const manifestPath = "docs/agrifabric-static-demo-clip-manifest.json";
const manifest = JSON.parse(fs.readFileSync(path.join(root, manifestPath), "utf8"));

function shellQuote(value) {
  return "'" + String(value).replaceAll("'", "'\\''") + "'";
}

function commandExists(command) {
  const result = spawnSync("bash", ["-lc", `command -v ${command}`], {
    encoding: "utf8",
  });
  return result.status === 0 ? result.stdout.trim() : "";
}

let failed = false;
const ffmpegPath = commandExists("ffmpeg");
const ffprobePath = commandExists("ffprobe");

const plans = manifest.clips.map((clip) => {
  const inputExists = fs.existsSync(path.join(root, clip.primary_asset));
  const thumbnailExists = fs.existsSync(path.join(root, clip.thumbnail));
  const outputDir = path.dirname(clip.planned_output);

  if (!inputExists || !thumbnailExists) failed = true;

  const command = [
    "ffmpeg",
    "-y",
    "-loop", "1",
    "-t", String(clip.target_seconds),
    "-i", clip.primary_asset,
    "-vf", "scale=1280:-2,zoompan=z='min(zoom+0.0007,1.08)':d=1:s=1280x720:fps=30,format=yuv420p",
    "-r", "30",
    "-an",
    clip.planned_output,
  ].map(shellQuote).join(" ");

  return {
    id: clip.id,
    target_seconds: clip.target_seconds,
    input: clip.primary_asset,
    input_exists: inputExists,
    thumbnail: clip.thumbnail,
    thumbnail_exists: thumbnailExists,
    planned_output: clip.planned_output,
    output_dir: outputDir,
    output_dir_exists: fs.existsSync(path.join(root, outputDir)),
    render_command: command,
  };
});

const summary = {
  schema_version: "agrifabric_static_demo_render_dry_run.v1",
  status: failed ? "FAILED" : "PASSED",
  ffmpeg_available: Boolean(ffmpegPath),
  ffmpeg_path: ffmpegPath || null,
  ffprobe_available: Boolean(ffprobePath),
  ffprobe_path: ffprobePath || null,
  rendering_executed: false,
  clip_count: plans.length,
  plans,
  note: "Dry run only. Commands are generated but not executed.",
};

console.log(JSON.stringify(summary, null, 2));
process.exit(failed ? 1 : 0);
