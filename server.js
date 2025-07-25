const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const fs = require('fs');
const path = require('path');
const QRCode = require('qrcode');
const helmet = require('helmet');
const compression = require('compression');
const rateLimit = require('express-rate-limit');
const { body, validationResult } = require('express-validator');
const { v4: uuidv4 } = require('uuid');
const moment = require('moment');

const app = express();
const PORT = process.env.PORT || 10000;

// Enhanced security and performance
app.use(helmet({
    contentSecurityPolicy: {
        directives: {
            defaultSrc: ["'self'"],
            styleSrc: ["'self'", "'unsafe-inline'"],
            scriptSrc: ["'self'", "'unsafe-inline'"],
            imgSrc: ["'self'", "data:", "https:"],
            connectSrc: ["'self'"]
        }
    },
    crossOriginEmbedderPolicy: false
}));

app.use(compression({
    level: 6,
    threshold: 1024
}));

// Rate limiting
const limiter = rateLimit({
    windowMs: parseInt(process.env.RATE_LIMIT_WINDOW) || 15 * 60 * 1000,
    max: parseInt(process.env.RATE_LIMIT_MAX_REQUESTS) || 100,
    message: {
        error: 'Too many requests, please try again later.'
    }
});

app.use('/api/', limiter);

// Enhanced CORS for Render
const corsOptions = {
    origin: [
        process.env.RENDER_EXTERNAL_URL,
        'https://upi-n9wg.onrender.com',
        'https://ritwik-pay.onrender.com',
        'http://localhost:3000',
        'http://localhost:10000'
    ].filter(Boolean),
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'Accept'],
    optionsSuccessStatus: 200
};

app.use(cors(corsOptions));

// Body parsing with larger limits
app.use(bodyParser.json({ limit: '50mb' }));
app.use(bodyParser.urlencoded({ extended: true, limit: '50mb' }));

// Static files with caching
app.use(express.static('public', {
    maxAge: '1d',
    etag: true
}));

// Trust proxy for Render
app.set('trust proxy', 1);

// Configuration from environment
const CONFIG = {
    upiId: process.env.UPI_ID || '7477772650@ibl',
    merchantName: process.env.MERCHANT_NAME || 'Ritwik Store',
    businessName: process.env.BUSINESS_NAME || 'Ritwik Jana',
    merchantCode: process.env.MERCHANT_CODE || 'RITWIK001',
    adminUsername: process.env.ADMIN_USERNAME || 'ritwik',
    adminPassword: process.env.ADMIN_PASSWORD || 'Ritwik@2025#SecureAdmin',
    autoVerifyEnabled: process.env.AUTO_VERIFY_ENABLED === 'true',
    autoVerifyDelay: parseInt(process.env.AUTO_VERIFY_DELAY) || 30000,
    paymentTimeout: parseInt(process.env.PAYMENT_TIMEOUT) || 600000,
    qrCodeSize: parseInt(process.env.QR_CODE_SIZE) || 256
};

// Data storage setup
const DATA_DIR = process.env.DATA_DIR || path.join(__dirname, 'data');
const PAYMENTS_FILE = path.join(DATA_DIR, 'payments.json');
const LOGS_FILE = path.join(DATA_DIR, 'gateway.log');

// Ensure data directory exists
if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
}

// Initialize payments file
if (!fs.existsSync(PAYMENTS_FILE)) {
    fs.writeFileSync(PAYMENTS_FILE, JSON.stringify([], null, 2));
}

// Enhanced helper functions
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
        // Create backup
        const backupFile = path.join(DATA_DIR, `payments_backup_${Date.now()}.json`);
        if (fs.existsSync(PAYMENTS_FILE)) {
            fs.copyFileSync(PAYMENTS_FILE, backupFile);
        }
        
        fs.writeFileSync(PAYMENTS_FILE, JSON.stringify(payments, null, 2));
        
        // Clean old backups (keep last 5)
        const backupFiles = fs.readdirSync(DATA_DIR)
            .filter(file => file.startsWith('payments_backup_'))
            .sort()
            .reverse();
        
        if (backupFiles.length > 5) {
            backupFiles.slice(5).forEach(file => {
                fs.unlinkSync(path.join(DATA_DIR, file));
            });
        }
        
        return true;
    } catch (error) {
        console.error('Error saving payments:', error);
        return false;
    }
}

function generateOrderId() {
    const timestamp = moment().format('YYYYMMDD_HHmmss');
    const uuid = uuidv4().split('-')[0].toUpperCase();
    return `${CONFIG.merchantCode}_${timestamp}_${uuid}`;
}

function generateUPILink(amount, orderId) {
    const params = new URLSearchParams({
        pa: CONFIG.upiId,
        pn: CONFIG.merchantName,
        am: amount.toString(),
        tr: orderId,
        cu: 'INR',
        tn: `Payment to ${CONFIG.businessName} - Order ${orderId}`
    });
    
    return `upi://pay?${params.toString()}`;
}

function logActivity(level, message, data = {}) {
    const logEntry = {
        timestamp: moment().toISOString(),
        level,
        message,
        data,
        service: 'upi-gateway'
    };
    
    console.log(JSON.stringify(logEntry));
    
    // Write to log file
    try {
        fs.appendFileSync(LOGS_FILE, JSON.stringify(logEntry) + '\n');
    } catch (error) {
        console.error('Failed to write to log file:', error);
    }
}

// Auto-verification function
function scheduleAutoVerification(orderId) {
    if (!CONFIG.autoVerifyEnabled) return;
    
    setTimeout(async () => {
        try {
            const payments = loadPayments();
            const payment = payments.find(p => p.orderId === orderId);
            
            if (payment && payment.status === 'pending') {
                // Simulate verification check (in real scenario, check with bank API/SMS)
                const shouldVerify = Math.random() > 0.7; // 30% auto-verify for demo
                
                if (shouldVerify) {
                    payment.status = 'paid';
                    payment.verifiedAt = moment().toISOString();
                    payment.verificationMethod = 'auto';
                    payment.utr = `AUTO_${Date.now()}`;
                    
                    savePayments(payments);
                    
                    logActivity('info', 'Payment auto-verified', {
                        orderId,
                        amount: payment.amount
                    });
                }
            }
        } catch (error) {
            logActivity('error', 'Auto-verification failed', { orderId, error: error.message });
        }
    }, CONFIG.autoVerifyDelay);
}

// Enhanced validation middleware
const validateCreateOrder = [
    body('amount').isFloat({ min: 1, max: 100000 }).withMessage('Amount must be between ₹1 and ₹100,000'),
    body('customerName').optional().isLength({ max: 100 }).withMessage('Name too long'),
    body('customerEmail').optional().isEmail().withMessage('Invalid email format')
];

const validateVerifyPayment = [
    body('orderId').notEmpty().withMessage('Order ID is required'),
    body('utr').isLength({ min: 8, max: 50 }).withMessage('Invalid UTR format')
];

// API Routes

// Enhanced health check
app.get('/health', (req, res) => {
    const health = {
        status: 'OK',
        timestamp: moment().toISOString(),
        service: 'ritwik-upi-gateway',
        version: '3.0.0',
        uptime: process.uptime(),
        memory: process.memoryUsage(),
        config: {
            upiId: CONFIG.upiId,
            merchantName: CONFIG.merchantName,
            autoVerifyEnabled: CONFIG.autoVerifyEnabled
        }
    };
    
    res.status(200).json(health);
});

// Home page
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Create payment order with enhanced features
app.post('/api/create-order', validateCreateOrder, async (req, res) => {
    try {
        const errors = validationResult(req);
        if (!errors.isEmpty()) {
            return res.status(400).json({
                success: false,
                error: 'Validation failed',
                details: errors.array()
            });
        }

        const { amount, customerName, customerEmail } = req.body;
        const orderId = generateOrderId();
        const upiLink = generateUPILink(amount, orderId);
        
        const payment = {
            orderId,
            amount: parseFloat(amount),
            customerName: customerName || 'Anonymous',
            customerEmail: customerEmail || '',
            upiLink,
            status: 'pending',
            createdAt: moment().toISOString(),
            expiresAt: moment().add(CONFIG.paymentTimeout, 'milliseconds').toISOString(),
            utr: null,
            verifiedAt: null,
            verificationMethod: null,
            ipAddress: req.ip,
            userAgent: req.get('User-Agent')
        };

        const payments = loadPayments();
        payments.unshift(payment); // Add to beginning for latest first
        
        if (!savePayments(payments)) {
            return res.status(500).json({
                success: false,
                error: 'Failed to save payment data'
            });
        }

        // Schedule auto-verification
        scheduleAutoVerification(orderId);
        
        logActivity('info', 'Payment order created', {
            orderId,
            amount,
            customerName
        });

        // Generate QR Code with enhanced options
        const qrOptions = {
            width: CONFIG.qrCodeSize,
            height: CONFIG.qrCodeSize,
            margin: 2,
            color: {
                dark: '#000000',
                light: '#FFFFFF'
            },
            errorCorrectionLevel: 'M'
        };

        QRCode.toDataURL(upiLink, qrOptions, (err, qrCode) => {
            const response = {
                success: true,
                orderId,
                amount: parseFloat(amount),
                upiLink,
                qrCode: err ? null : qrCode,
                expiresAt: payment.expiresAt,
                message: 'Payment link generated successfully',
                autoVerifyEnabled: CONFIG.autoVerifyEnabled
            };

            if (err) {
                logActivity('warn', 'QR Code generation failed', { orderId, error: err.message });
            }

            res.json(response);
        });

    } catch (error) {
        logActivity('error', 'Order creation failed', { error: error.message });
        res.status(500).json({
            success: false,
            error: 'Internal server error'
        });
    }
});

// Enhanced payment verification
app.post('/api/verify-payment', validateVerifyPayment, (req, res) => {
    try {
        const errors = validationResult(req);
        if (!errors.isEmpty()) {
            return res.status(400).json({
                success: false,
                error: 'Validation failed',
                details: errors.array()
            });
        }

        const { orderId, utr } = req.body;
        const payments = loadPayments();
        const paymentIndex = payments.findIndex(p => p.orderId === orderId);
        
        if (paymentIndex === -1) {
            return res.status(404).json({
                success: false,
                error: 'Order not found'
            });
        }

        const payment = payments[paymentIndex];
        
        // Check if expired
        if (moment().isAfter(payment.expiresAt)) {
            return res.status(400).json({
                success: false,
                error: 'Payment link has expired'
            });
        }
        
        if (payment.status === 'paid') {
            return res.json({
                success: true,
                message: 'Payment already verified',
                status: 'paid',
                orderId,
                amount: payment.amount,
                verifiedAt: payment.verifiedAt
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
        payments[paymentIndex].verifiedAt = moment().toISOString();
        payments[paymentIndex].verificationMethod = 'manual';
        payments[paymentIndex].verifierIp = req.ip;
        
        if (!savePayments(payments)) {
            return res.status(500).json({
                success: false,
                error: 'Failed to update payment status'
            });
        }

        logActivity('info', 'Payment verified manually', {
            orderId,
            utr,
            amount: payment.amount
        });

        res.json({
            success: true,
            message: 'Payment verified successfully',
            status: 'paid',
            orderId,
            amount: payment.amount,
            verifiedAt: payments[paymentIndex].verifiedAt,
            redirectUrl: `${process.env.RENDER_EXTERNAL_URL}/success?order=${orderId}`
        });

    } catch (error) {
        logActivity('error', 'Payment verification failed', { error: error.message });
        res.status(500).json({
            success: false,
            error: 'Internal server error'
        });
    }
});

// Enhanced payment status with auto-refresh
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

        const isExpired = moment().isAfter(payment.expiresAt);
        
        res.json({
            success: true,
            payment: {
                orderId: payment.orderId,
                amount: payment.amount,
                status: isExpired && payment.status === 'pending' ? 'expired' : payment.status,
                createdAt: payment.createdAt,
                expiresAt: payment.expiresAt,
                verifiedAt: payment.verifiedAt,
                verificationMethod: payment.verificationMethod,
                timeRemaining: isExpired ? 0 : moment(payment.expiresAt).diff(moment(), 'seconds')
            }
        });

    } catch (error) {
        logActivity('error', 'Status check failed', { error: error.message });
        res.status(500).json({
            success: false,
            error: 'Internal server error'
        });
    }
});

// Admin routes with enhanced security
app.post('/api/admin/login', (req, res) => {
    const { username, password } = req.body;
    
    if (username === CONFIG.adminUsername && password === CONFIG.adminPassword) {
        logActivity('info', 'Admin login successful', { username, ip: req.ip });
        res.json({
            success: true,
            message: 'Login successful',
            sessionId: uuidv4()
        });
    } else {
        logActivity('warn', 'Admin login failed', { username, ip: req.ip });
        res.status(401).json({
            success: false,
            error: 'Invalid credentials'
        });
    }
});

// Enhanced admin payments view
app.get('/api/admin/payments', (req, res) => {
    try {
        const { page = 1, limit = 50, status, search } = req.query;
        let payments = loadPayments();
        
        // Filter by status
        if (status && status !== 'all') {
            payments = payments.filter(p => p.status === status);
        }
        
        // Search functionality
        if (search) {
            payments = payments.filter(p => 
                p.orderId.toLowerCase().includes(search.toLowerCase()) ||
                p.customerName.toLowerCase().includes(search.toLowerCase()) ||
                (p.utr && p.utr.toLowerCase().includes(search.toLowerCase()))
            );
        }
        
        // Pagination
        const startIndex = (page - 1) * limit;
        const endIndex = startIndex + parseInt(limit);
        const paginatedPayments = payments.slice(startIndex, endIndex);
        
        // Statistics
        const stats = {
            total: payments.length,
            pending: payments.filter(p => p.status === 'pending').length,
            paid: payments.filter(p => p.status === 'paid').length,
            expired: payments.filter(p => 
                p.status === 'pending' && moment().isAfter(p.expiresAt)
            ).length,
            totalRevenue: payments
                .filter(p => p.status === 'paid')
                .reduce((sum, p) => sum + p.amount, 0)
        };
        
        res.json({
            success: true,
            payments: paginatedPayments,
            pagination: {
                currentPage: parseInt(page),
                totalPages: Math.ceil(payments.length / limit),
                totalItems: payments.length,
                itemsPerPage: parseInt(limit)
            },
            stats
        });
        
    } catch (error) {
        logActivity('error', 'Admin payments fetch failed', { error: error.message });
        res.status(500).json({
            success: false,
            error: 'Internal server error'
        });
    }
});

// Manual admin verification
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
        payments[paymentIndex].verifiedAt = moment().toISOString();
        payments[paymentIndex].verificationMethod = 'admin';
        payments[paymentIndex].adminVerifierIp = req.ip;
        
        if (!savePayments(payments)) {
            return res.status(500).json({
                success: false,
                error: 'Failed to update payment status'
            });
        }

        logActivity('info', 'Payment verified by admin', {
            orderId,
            amount: payments[paymentIndex].amount,
            adminIp: req.ip
        });

        res.json({
            success: true,
            message: 'Payment marked as verified'
        });

    } catch (error) {
        logActivity('error', 'Admin verification failed', { error: error.message });
        res.status(500).json({
            success: false,
            error: 'Internal server error'
        });
    }
});

// Success page redirect
app.get('/success', (req, res) => {
    const orderId = req.query.order;
    res.send(`
        <!DOCTYPE html>
        <html>
        <head>
            <title>Payment Successful</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f0f8ff; }
                .success-container { background: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); max-width: 500px; margin: 0 auto; }
                .success-icon { font-size: 64px; color: #28a745; margin-bottom: 20px; }
                h1 { color: #28a745; margin-bottom: 10px; }
                .order-id { background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0; font-family: monospace; }
                .back-btn { background: #007bff; color: white; padding: 12px 24px; border: none; border-radius: 8px; text-decoration: none; display: inline-block; margin-top: 20px; }
            </style>
        </head>