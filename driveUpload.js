const { google } = require('googleapis');
const fs = require('fs');
const path = require('path');

/**
 * Upload a file to Google Drive
 * @param {object} auth - Google Auth client
 * @param {string} filePath - Local path to file
 * @param {string} parentFolderId - Drive folder ID
 */


async function uploadToDrive(auth, filePath, parentFolderId, driveFileName) {
  const drive = google.drive({ version: 'v3', auth });

  const response = await drive.files.create({
    supportsAllDrives: true,
    requestBody: {
      name: driveFileName,
      parents: [parentFolderId]
    },
    media: {
      mimeType: 'audio/wav',
      body: fs.createReadStream(filePath)
    },
    fields: 'id'
  });

  console.log(`Uploaded ${driveFileName}`);
  console.log('Drive upload response:', response.data);
}


module.exports = { uploadToDrive };
