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

// Security and performance
app.use(helmet({
    contentSecurityPolicy: false,
    crossOriginEmbedderPolicy: false
}));
app.use(compression());

// CORS configuration
const corsOptions = {
    origin: [
        process.env.RENDER_EXTERNAL_URL,
        'https://upi-n9wg.onrender.com',
        'http://localhost:3000',
        'http://localhost:10000'
    ].filter(Boolean),
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'Accept']
};

app.use(cors(corsOptions));

// Body parsing
app.use(bodyParser.json({ limit: '10mb' }));
app.use(bodyParser.urlencoded({ extended: true, limit: '10mb' }));

// Static files
app.use(express.static('public'));

// Trust proxy
app.set('trust proxy', 1);

// Configuration
const CONFIG = {
    upiId: process.env.UPI_ID || '7477772650@ibl',
    merchantName: process.env.MERCHANT_NAME || 'Ritwik Store',
    businessName: process.env.BUSINESS_NAME || 'Ritwik Jana',
    adminUsername: process.env.ADMIN_USERNAME || 'ritwik',
    adminPassword: process.env.ADMIN_PASSWORD || 'Ritwik@2025#Secure'
};

// Data storage
const DATA_DIR = process.env.DATA_DIR || path.join(__dirname, 'data');
const PAYMENTS_FILE = path.join(DATA_DIR, 'payments.json');

// Ensure directories exist
if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
}

if (!fs.existsSync(PAYMENTS_FILE)) {
    fs.writeFileSync(PAYMENTS_FILE, JSON.stringify([], null, 2));
}

// Helper functions
function loadPayments() {
    try {
        const data = fs.readFileSync(PAYMENTS_FILE, 'utf8');
        return JSON.parse(data);
    } catch (error) {
        console.error('Error loading payments:', error);
        return [];
    }
}

function savePayments(payments) {
    try {
        fs.writeFileSync(PAYMENTS_FILE, JSON.stringify(payments, null, 2));
        return true;
    } catch (error) {
        console.error('Error saving payments:', error);
        return false;
    }
}

function generateOrderId() {
    const now = new Date();
    const timestamp = now.toISOString().replace(/[-:T.]/g, '').slice(0, 14);
    const random = Math.floor(Math.random() * 1000).toString().padStart(3, '0');
    return `ORD_${timestamp}_${random}`;
}

function generateUPILink(amount, orderId) {
    return `upi://pay?pa=${CONFIG.upiId}&pn=${CONFIG.merchantName}&am=${amount}&tr=${orderId}&cu=INR&tn=Payment to ${CONFIG.businessName}`;
}

// Auto-verification simulation
function scheduleAutoVerification(orderId) {
    setTimeout(async () => {
        try {
            const payments = loadPayments();
            const paymentIndex = payments.findIndex(p => p.orderId === orderId);
            
            if (paymentIndex !== -1 && payments[paymentIndex].status === 'pending') {
                // 40% chance of auto-verification (simulation)
                if (Math.random() > 0.6) {
                    payments[paymentIndex].status = 'paid';
                    payments[paymentIndex].verifiedAt = new Date().toISOString();
                    payments[paymentIndex].verificationMethod = 'auto';
                    payments[paymentIndex].utr = `AUTO_${Date.now()}`;
                    
                    savePayments(payments);
                    console.log(`Auto-verified payment: ${orderId}`);
                }
            }
        } catch (error) {
            console.error('Auto-verification error:', error);
        }
    }, 30000); // 30 seconds delay
}

// Routes

// Health check
app.get('/health', (req, res) => {
    res.status(200).json({
        status: 'OK',
        timestamp: new Date().toISOString(),
        service: 'ritwik-upi-gateway',
        version: '3.0.0',
        config: {
            upiId: CONFIG.upiId,
            merchantName: CONFIG.merchantName
        }
    });
});

// Home page
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Create payment order
app.post('/api/create-order', (req, res) => {
    try {
        const { amount, customerName, customerEmail } = req.body;
        
        if (!amount || amount <= 0) {
            return res.status(400).json({
                success: false,
                error: 'Invalid amount'
            });
        }

        const orderId = generateOrderId();
        const upiLink = generateUPILink(amount, orderId);
        
        const payment = {
            orderId,
            amount: parseFloat(amount),
            customerName: customerName || 'Anonymous',
            customerEmail: customerEmail || '',
            upiLink,
            status: 'pending',
            createdAt: new Date().toISOString(),
            expiresAt: new Date(Date.now() + 600000).toISOString(), // 10 minutes
            utr: null,
            verifiedAt: null,
            verificationMethod: null
        };

        const payments = loadPayments();
        payments.unshift(payment);
        
        if (!savePayments(payments)) {
            return res.status(500).json({
                success: false,
                error: 'Failed to save payment data'
            });
        }

        // Schedule auto-verification
        scheduleAutoVerification(orderId);

        // Generate QR Code
        QRCode.toDataURL(upiLink, { width: 256, margin: 2 }, (err, qrCode) => {
            const response = {
                success: true,
                orderId,
                amount: parseFloat(amount),
                upiLink,
                qrCode: err ? null : qrCode,
                expiresAt: payment.expiresAt,
                message: 'Payment link generated successfully'
            };

            res.json(response);
        });

    } catch (error) {
        console.error('Error creating order:', error);
        res.status(500).json({
            success: false,
            error: 'Internal server error'
        });
    }
});

// Verify payment
app.post('/api/verify-payment', (req, res) => {
    try {
        const { orderId, utr } = req.body;
        
        if (!orderId || !utr) {
            return res.status(400).json({
                success: false,
                error: 'Order ID and UTR are required'
            });
        }

        const payments = loadPayments();
        const paymentIndex = payments.findIndex(p => p.orderId === orderId);
        
        if (paymentIndex === -1) {
            return res.status(404).json({
                success: false,
                error: 'Order not found'
            });
        }

        const payment = payments[paymentIndex];
        
        if (payment.status === 'paid') {
            return res.json({
                success: true,
                message: 'Payment already verified',
                status: 'paid',
                orderId,
                amount: payment.amount
            });
        }

        // Check duplicate UTR
        const existingUTR = payments.find(p => p.utr === utr && p.utr !== null);
        if (existingUTR) {
            return res.status(400).json({
                success: false,
                error: 'This UTR has already been used'
            });
        }

        // Mark as verified
        payments[paymentIndex].utr = utr;
        payments[paymentIndex].status = 'paid';
        payments[paymentIndex].verifiedAt = new Date().toISOString();
        payments[paymentIndex].verificationMethod = 'manual';
        
        if (!savePayments(payments)) {
            return res.status(500).json({
                success: false,
                error: 'Failed to update payment status'
            });
        }

        res.json({
            success: true,
            message: 'Payment verified successfully',
            status: 'paid',
            orderId,
            amount: payment.amount
        });

    } catch (error) {
        console.error('Error verifying payment:', error);
        res.status(500).json({
            success: false,
            error: 'Internal server error'
        });
    }
});

// Get payment status
app.get('/api/payment-status/:orderId', (req, res) => {
    try {
        const { orderId } = req.params;
        const payments = loadPayments();
        const payment = payments.find(p => p.orderId === orderId);
        
        if (!payment) {
            return res.status(404).json({
                success: false,
                error: 'Order not found'
            });
        }

        const isExpired = new Date() > new Date(payment.expiresAt);
        
        res.json({
            success: true,
            payment: {
                orderId: payment.orderId,
                amount: payment.amount,
                status: isExpired && payment.status === 'pending' ? 'expired' : payment.status,
                createdAt: payment.createdAt,
                expiresAt: payment.expiresAt,
                verifiedAt: payment.verifiedAt,
                timeRemaining: isExpired ? 0 : Math.max(0, Math.floor((new Date(payment.expiresAt) - new Date()) / 1000))
            }
        });

    } catch (error) {
        console.error('Error getting payment status:', error);
        res.status(500).json({
            success: false,
            error: 'Internal server error'
        });
    }
});

// Admin login
app.post('/api/admin/login', (req, res) => {
    const { username, password } = req.body;
    
    if (username === CONFIG.adminUsername && password === CONFIG.adminPassword) {
        res.json({
            success: true,
            message: 'Login successful'
        });
    } else {
        res.status(401).json({
            success: false,
            error: 'Invalid credentials'
        });
    }
});

// Get all payments (admin)
app.get('/api/admin/payments', (req, res) => {
    try {
        const payments = loadPayments();
        
        // Calculate statistics
        const stats = {
            total: payments.length,
            pending: payments.filter(p => p.status === 'pending').length,
            paid: payments.filter(p => p.status === 'paid').length,
            totalRevenue: payments
                .filter(p => p.status === 'paid')
                .reduce((sum, p) => sum + p.amount, 0)
        };
        
        res.json({
            success: true,
            payments: payments.reverse(), // Latest first
            stats
        });
    } catch (error) {
        console.error('Error getting payments:', error);
        res.status(500).json({
            success: false,
            error: 'Internal server error'
        });
    }
});

// Admin verify payment
app.post('/api/admin/verify-payment', (req, res) => {
    try {
        const { orderId } = req.body;
        const payments = loadPayments();
        const paymentIndex = payments.findIndex(p => p.orderId === orderId);
        
        if (paymentIndex === -1) {
            return res.status(404).json({
                success: false,
                error: 'Order not found'
            });
        }

        payments[paymentIndex].status = 'paid';
        payments[paymentIndex].verifiedAt = new Date().toISOString();
        payments[paymentIndex].verificationMethod = 'admin';
        
        if (!savePayments(payments)) {
            return res.status(500).json({
                success: false,
                error: 'Failed to update payment status'
            });
        }

        res.json({
            success: true,
            message: 'Payment marked as verified'
        });

    } catch (error) {
        console.error('Error verifying payment:', error);
        res.status(500).json({
            success: false,
            error: 'Internal server error'
        });
    }
});

// Success page
app.get('/success', (req, res) => {
    const orderId = req.query.order;
    const html = `
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Payment Successful</title>
        <style>
            body { 
                font-family: 'Segoe UI', sans-serif; 
                background: linear-gradient(135deg, #28a745, #20c997); 
                min-height: 100vh; 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                margin: 0; 
                padding: 20px; 
            }
            .container { 
                background: white; 
                padding: 40px; 
                border-radius: 15px; 
                box-shadow: 0 20px 40px rgba(0,0,0,0.1); 
                text-align: center; 
                max-width: 500px; 
                width: 100%; 
            }
            .success-icon { 
                font-size: 64px; 
                color: #28a745; 
                margin-bottom: 20px; 
            }
            h1 { 
                color: #28a745; 
                margin-bottom: 15px; 
            }
            .order-info { 
                background: #f8f9fa; 
                padding: 20px; 
                border-radius: 10px; 
                margin: 20px 0; 
                font-family: monospace; 
            }
            .back-btn { 
                background: linear-gradient(135deg, #007bff, #0056b3); 
                color: white; 
                padding: 12px 24px; 
                border: none; 
                border-radius: 8px; 
                text-decoration: none; 
                display: inline-block; 
                margin-top: 20px; 
                transition: transform 0.3s ease; 
            }
            .back-btn:hover { 
                transform: translateY(-2px); 
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="success-icon">✅</div>
            <h1>Payment Successful!</h1>
            <p>Your payment has been processed and verified successfully.</p>
            ${orderId ? `<div class="order-info">Order ID: ${orderId}</div>` : ''}
            <p>Thank you for choosing ${CONFIG.businessName}!</p>
            <a href="/" class="back-btn">← Back to Home</a>
        </div>
    </body>
    </html>`;
    
    res.send(html);
});

// Failure page
app.get('/failure', (req, res) => {
    const html = `
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Payment Failed</title>
        <style>
            body { 
                font-family: 'Segoe UI', sans-serif; 
                background: linear-gradient(135deg, #dc3545, #c82333); 
                min-height: 100vh; 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                margin: 0; 
                padding: 20px; 
            }
            .container { 
                background: white; 
                padding: 40px; 
                border-radius: 15px; 
                box-shadow: 0 20px 40px rgba(0,0,0,0.1); 
                text-align: center; 
                max-width: 500px; 
                width: 100%; 
            }
            .failure-icon { 
                font-size: 64px; 
                color: #dc3545; 
                margin-bottom: 20px; 
            }
            h1 { 
                color: #dc3545; 
                margin-bottom: 15px; 
            }
            .back-btn { 
                background: linear-gradient(135deg, #007bff, #0056b3); 
                color: white; 
                padding: 12px 24px; 
                border: none; 
                border-radius: 8px; 
                text-decoration: none; 
                display: inline-block; 
                margin-top: 20px; 
                transition: transform 0.3s ease; 
            }
            .back-btn:hover { 
                transform: translateY(-2px); 
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="failure-icon">❌</div>
            <h1>Payment Failed</h1>
            <p>We couldn't process your payment. Please try again.</p>
            <a href="/" class="back-btn">← Try Again</a>
        </div>
    </body>
    </html>`;
    
    res.send(html);
});

// Webhook endpoint
app.post('/api/webhook', (req, res) => {
    console.log('Webhook received:', req.body);
    res.json({ success: true });
});

// Error handling
app.use((err, req, res, next) => {
    console.error('Unhandled error:', err);
    res.status(500).json({
        success: false,
        error: 'Something went wrong!'
    });
});

// 404 handler
app.use((req, res) => {
    res.status(404).json({
        success: false,
        error: 'Route not found'
    });
});

// Graceful shutdown
process.on('SIGTERM', () => {
    console.log('Server shutting down gracefully');
    process.exit(0);
});

process.on('SIGINT', () => {
    console.log('Server interrupted');
    process.exit(0);
});

// Start server
app.listen(PORT, '0.0.0.0', () => {
    console.log(`🚀 Ritwik's UPI Gateway v3.0 running on port ${PORT}`);
    console.log(`📱 Main Site: http://localhost:${PORT}`);
    console.log(`🔐 Admin Panel: http://localhost:${PORT}/admin.html`);
    console.log(`💳 UPI ID: ${CONFIG.upiId}`);
    console.log(`🏪 Merchant: ${CONFIG.merchantName}`);
    console.log(`Environment: ${process.env.NODE_ENV || 'development'}`);
});
