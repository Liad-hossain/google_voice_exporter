const { GoogleAuth } = require("google-auth-library");
const axios = require("axios");
const fs = require("fs");
const path = require("path");
const AdmZip = require("adm-zip");
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

function extractZipFiles(zipPath) {
  try {
    console.log("Starting ZIP extraction with adm-zip...");
    const zip = new AdmZip(zipPath);

    // Log ZIP contents before extraction
    const zipEntries = zip.getEntries();
    console.log(`ZIP contains ${zipEntries.length} entries:`);
    zipEntries.forEach((entry, index) => {
      console.log(
        `  ${index + 1}. ${entry.entryName} (${entry.getData().length} bytes)`,
      );
    });

    zip.extractAllTo(EXTRACT_DIR, true);

    console.log("ZIP extracted successfully");
    const extractedFiles = fs.readdirSync(EXTRACT_DIR);
    console.log("Files in extract dir:", extractedFiles);

    if (extractedFiles.length === 0) {
      console.log("Warning: No files were extracted from the ZIP");
    }
  } catch (extractError) {
    console.error("ZIP extraction failed:", extractError.message);
    console.log("Checking if the downloaded file is actually a ZIP...");

    // Check file type
    const fileBuffer = fs.readFileSync(zipPath);
    const fileSignature = fileBuffer.slice(0, 4).toString("hex");
    console.log("File signature (first 4 bytes):", fileSignature);

    // ZIP files start with '504b' (PK)
    if (
      fileSignature !== "504b0304" &&
      fileSignature !== "504b0506" &&
      fileSignature !== "504b0708"
    ) {
      console.log("Downloaded file is not a valid ZIP file!");
      console.log("File might be an MBOX file or other format.");
      console.log("Renaming to .mbox for inspection...");
      const mboxPath = path.join(TEMP_DIR, "export.mbox");
      fs.renameSync(zipPath, mboxPath);
      console.log("File renamed to:", mboxPath);
    }

    throw extractError;
  }
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

  console.log(
    "Download completed. File size:",
    fs.statSync(zipPath).size,
    "bytes",
  );

  extractZipFiles(zipPath);

  // --- Upload audio files ---
  const files = fs.readdirSync(EXTRACT_DIR, { recursive: true });
  console.log("All files found:", files);

  for (const file of files) {
    console.log("Checking file:", file);
    if (file.endsWith(".wav") || file.endsWith(".mp3")) {
      console.log("Uploading file:", file);
      const fullPath = path.join(EXTRACT_DIR, file);
      const fileName = buildFilename(path.basename(file));
      await uploadToDrive(
        auth,
        fullPath,
        process.env.DRIVE_FOLDER_ID,
        fileName,
      );
    } else {
      console.log("Skipping file (not audio):", file);
    }
  }

  console.log("All recordings uploaded");
}

run().catch((err) => {
  console.error(err.response?.data || err);
  process.exit(1);
});
