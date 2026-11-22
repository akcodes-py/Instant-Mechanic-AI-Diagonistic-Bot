// Rich diagnostic context for the assigned mechanic. No raw binaries: media
// bytes live in S3/MinIO (dev) and only object keys / URLs are stored here.
// Run with: mongosh < contracts/db/mongodb.js

db = db.getSiblingDB('instant_mechanic');

db.createCollection('chat_messages');
db.chat_messages.createIndex({ session_id: 1, created_at: 1 });
db.chat_messages.createIndex({ booking_id: 1 });

db.createCollection('uploaded_media');
db.uploaded_media.createIndex({ session_id: 1, created_at: 1 });
db.uploaded_media.createIndex({ booking_id: 1 });
db.uploaded_media.createIndex({ object_key: 1 }, { unique: true, sparse: true });

/* Example uploaded_media document
{
  _id: ObjectId(),
  booking_id: UUID('...'),
  session_id: UUID('...'),
  kind: 'image',
  object_key: 'uploads/2026/11/22/<uuid>.jpg',
  mime_type: 'image/jpeg',
  size_bytes: 182341,
  analyzed: true,
  detections: [
    { label: 'Check Engine', confidence: 0.91, box: [12, 34, 210, 188], reliable: true }
  ],
  reliable_labels: ['Check Engine'],
  created_at: ISODate()
}
*/
