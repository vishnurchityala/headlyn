const express = require('express');
const dotenv = require('dotenv');
const { getApp, getApps, initializeApp } = require('firebase/app');
const {
  doc,
  getFirestore: getClientFirestore,
  runTransaction
} = require('firebase/firestore');
const path = require('node:path');

const ROOT_DIR = __dirname;
const PORT = Number(process.env.PORT) || 3000;
const EMAIL_PATTERN = /^[^\s@/]+@[^\s@/]+\.[^\s@/]{2,}$/i;
const REGISTRATIONS_COLLECTION = 'newsletter_registrations';

// Deployment-provided environment variables win. For local development,
// dotenv fills in values that are missing from process.env using .env.
dotenv.config({ path: path.join(ROOT_DIR, '.env'), quiet: true });

const app = express();

app.use((request, response, next) => {
  response.setHeader('Access-Control-Allow-Origin', '*');
  response.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  response.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  response.setHeader('Access-Control-Max-Age', '86400');

  if (request.method === 'OPTIONS') {
    return response.sendStatus(204);
  }

  return next();
});

app.use(express.json({ limit: '10kb' }));

function normalizeEmail(value) {
  return typeof value === 'string' ? value.trim().toLowerCase() : '';
}

function firebaseIsConfigured() {
  return [
    'FIREBASE_API_KEY',
    'FIREBASE_AUTH_DOMAIN',
    'FIREBASE_PROJECT_ID',
    'FIREBASE_STORAGE_BUCKET',
    'FIREBASE_SENDER_ID',
    'FIREBASE_APP_ID'
  ].every((name) => Boolean(process.env[name]));
}

function getFirestore() {
  if (!firebaseIsConfigured()) {
    throw new Error('Firebase configuration is incomplete.');
  }

  const firebaseConfig = {
    apiKey: process.env.FIREBASE_API_KEY,
    authDomain: process.env.FIREBASE_AUTH_DOMAIN,
    projectId: process.env.FIREBASE_PROJECT_ID,
    storageBucket: process.env.FIREBASE_STORAGE_BUCKET,
    messagingSenderId: process.env.FIREBASE_SENDER_ID,
    appId: process.env.FIREBASE_APP_ID
  };
  const firebaseApp = getApps().length > 0
    ? getApp()
    : initializeApp(firebaseConfig);

  return getClientFirestore(firebaseApp);
}

app.get('/api/health', (_request, response) => {
  response.json({
    ok: true,
    firebaseConfigured: firebaseIsConfigured()
  });
});

app.post('/api/register', async (request, response) => {
  const email = normalizeEmail(request.body?.email);

  if (email.length > 254 || !EMAIL_PATTERN.test(email)) {
    return response.status(400).json({
      error: 'Please provide a valid email address.'
    });
  }

  if (!firebaseIsConfigured()) {
    return response.status(503).json({
      error: 'Firebase registration storage is not configured.'
    });
  }

  const registration = {
    email,
    approved: false,
    createdAt: new Date().toISOString()
  };

  try {
    const database = getFirestore();
    const registrationReference = doc(database, REGISTRATIONS_COLLECTION, email);

    await runTransaction(database, async (transaction) => {
      const existingRegistration = await transaction.get(registrationReference);

      if (existingRegistration.exists()) {
        const duplicateError = new Error('This email is already registered.');
        duplicateError.code = 'DUPLICATE_REGISTRATION';
        throw duplicateError;
      }

      transaction.set(registrationReference, registration);
    });

    return response.status(201).json({
      message: 'Registration received. Newsletter access is pending approval.',
      registration: {
        email: registration.email,
        approved: registration.approved
      }
    });
  } catch (error) {
    if (error.code === 'DUPLICATE_REGISTRATION') {
      return response.status(409).json({
        error: 'This email is already registered.'
      });
    }

    console.error('Unable to save registration:', error);
    return response.status(500).json({
      error: 'Unable to save your registration right now.'
    });
  }
});

app.get('/', (_request, response) => {
  response.sendFile(path.join(ROOT_DIR, 'index.html'));
});

app.use('/assets', express.static(path.join(ROOT_DIR, 'assets'), {
  dotfiles: 'deny'
}));

module.exports = app;

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`Headlyn server running at http://localhost:${PORT}`);
  });
}
