const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const fs = require('fs');
const path = require('path');
const QRCode = require('qrcode');
const helmet = require('helmet');
const compression = require('compression');

const app = express();
const PORT = process.env.PORT || 10000;

// Production security and performance
app.use(helmet());
app.use(compression());

// CORS configuration for production
const corsOptions = {
    origin: process.env.NODE_ENV === 'production' 
        ? ['https://your-domain.onrender.com'] 
        : true,
    credentials: true
};

app.use(cors(corsOptions));
app.use(bodyParser.json({ limit: '10mb' }));
app.use(bodyParser.urlencoded({ extended: true, limit: '10mb' }));

// Serve static files
app.use(express.static('public'));

// Health check endpoint for Render
app.get('/health', (req, res) => {
    res.status(200).json({ 
        status: 'OK', 
        timestamp: new Date().toISOString(),
        service: 'upi-payment-gateway'
    });
});

// Configuration from environment variables
const CONFIG = {
    upiId: process.env.UPI_ID || 'yourupi@upi',
    merchantName: process.env.MERCHANT_NAME || 'YourShop',
    adminUsername: process.env.ADMIN_USERNAME || 'admin',
    adminPassword: process.env.ADMIN_PASSWORD || 'admin123'
};

// Data directory for persistent storage
const DATA_DIR = process.env.DATA_DIR || path.join(__dirname, 'data');
const PAYMENTS_FILE = path.join(DATA_DIR, 'payments.json');

// Ensure data directory exists
if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
}

// Initialize payments file
if (!fs.existsSync(PAYMENTS_FILE)) {
    fs.writeFileSync(PAYMENTS_FILE, JSON.stringify([], null, 2));
}

// Rest of your existing server code...
// (Keep all the existing helper functions and routes)

// Graceful shutdown
process.on('SIGTERM', () => {
    console.log('SIGTERM received, shutting down gracefully');
    process.exit(0);
});

// Start server
app.listen(PORT, '0.0.0.0', () => {
    console.log(`🚀 UPI Payment Gateway running on port ${PORT}`);
    console.log(`📱 Health check: http://localhost:${PORT}/health`);
    console.log(`🔐 Admin panel: http://localhost:${PORT}/admin.html`);
    console.log(`🌍 Environment: ${process.env.NODE_ENV || 'development'}`);
});
