const { GoogleAuth } = require("google-auth-library");
const axios = require("axios");
const fs = require("fs");
const path = require("path");
const unzipper = require("unzipper");
const { uploadToDrive } = require("./driveUpload");

const TEMP_DIR = "./temp";
const EXTRACT_DIR = "./temp/extracted";

function extractPhoneNumber(filename) {
  const match = filename.match(/\+\d{6,15}/);
  return match ? match[0] : "unknown";
}

function getTimestamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function buildFilename(originalFilename) {
  const phone = extractPhoneNumber(originalFilename);
  const timestamp = getTimestamp();

  return `call_${phone}_${timestamp}.wav`;
}

async function run() {
  fs.mkdirSync(EXTRACT_DIR, { recursive: true });

  // --- Auth ---
  const key = JSON.parse(process.env.GOOGLE_SERVICE_ACCOUNT_JSON);

  const auth = new GoogleAuth({
    credentials: key,
    scopes: [
      "https://www.googleapis.com/auth/ediscovery",
      "https://www.googleapis.com/auth/devstorage.read_only",
      "https://www.googleapis.com/auth/drive.file",
    ],
    clientOptions: {
      subject: process.env.WORKSPACE_ADMIN_EMAIL,
    },
  });

  const client = await auth.getClient();
  const token = await client.getAccessToken();

  // --- Get latest completed export ---
  const exportsRes = await axios.get(
    `https://vault.googleapis.com/v1/matters/${process.env.VAULT_MATTER_ID}/exports`,
    { headers: { Authorization: `Bearer ${token.token}` } },
  );

  const completedExport = exportsRes.data.exports.find(
    (e) => e.status === "COMPLETED",
  );

  if (!completedExport) {
    console.log("No completed export found");
    return;
  }

  const file = completedExport.cloudStorageSink.files[0];
  const gcsUrl = `https://storage.googleapis.com/${file.bucketName}/${file.objectName}`;

  console.log("Downloading:", gcsUrl);

  // --- Download ZIP ---
  const zipPath = path.join(TEMP_DIR, "export.zip");
  const zipStream = fs.createWriteStream(zipPath);

  const zipRes = await axios.get(gcsUrl, {
    responseType: "stream",
    headers: { Authorization: `Bearer ${token.token}` },
  });

  await new Promise((resolve, reject) => {
    zipRes.data.pipe(zipStream);
    zipStream.on("finish", resolve);
    zipStream.on("error", reject);
  });

  // --- Extract ZIP ---
  await fs
    .createReadStream(zipPath)
    .pipe(unzipper.Extract({ path: EXTRACT_DIR }))
    .promise();

  console.log("ZIP extracted");
  console.log('Files in extract dir:', fs.readdirSync(EXTRACT_DIR));


  // --- Upload audio files ---
  const files = fs.readdirSync(EXTRACT_DIR, { recursive: true });

  for (const file of files) {
    if (file.endsWith(".wav") || file.endsWith(".mp3")) {
      const fullPath = path.join(EXTRACT_DIR, file);
      const fileName = buildFilename(path.basename(file));
      await uploadToDrive(
        auth,
        fullPath,
        process.env.DRIVE_FOLDER_ID,
        fileName,
      );
    }
  }

  console.log("All recordings uploaded");
}

run().catch((err) => {
  console.error(err.response?.data || err);
  process.exit(1);
});
