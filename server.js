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

// Security
app.use(helmet({
    contentSecurityPolicy: false,
    crossOriginEmbedderPolicy: false
}));
app.use(compression());

// CORS - Allow all origins for testing
app.use(cors({
    origin: true,
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'Accept']
}));

// Body parsing
app.use(bodyParser.json({ limit: '50mb' }));
app.use(bodyParser.urlencoded({ extended: true, limit: '50mb' }));

// Static files
app.use(express.static(path.join(__dirname, 'public')));

// Trust proxy for Render
app.set('trust proxy', 1);

// Configuration
const CONFIG = {
    upiId: process.env.UPI_ID || '7477772650@ibl',
    merchantName: process.env.MERCHANT_NAME || 'Ritwik Store',
    businessName: process.env.BUSINESS_NAME || 'Ritwik Jana',
    adminUsername: process.env.ADMIN_USERNAME || 'ritwik',
    adminPassword: process.env.ADMIN_PASSWORD || 'admin123'
};

// Data file path
const PAYMENTS_FILE = path.join(__dirname, 'payments.json');

// Initialize payments file
if (!fs.existsSync(PAYMENTS_FILE)) {
    try {
        fs.writeFileSync(PAYMENTS_FILE, JSON.stringify([], null, 2));
        console.log('✅ Payments file created');
    } catch (error) {
        console.error('❌ Error creating payments file:', error);
    }
}

// Helper functions
function loadPayments() {
    try {
        if (!fs.existsSync(PAYMENTS_FILE)) {
            return [];
        }
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
        console.log('✅ Payments saved successfully');
        return true;
    } catch (error) {
        console.error('❌ Error saving payments:', error);
        return false;
    }
}

function generateOrderId() {
    const timestamp = Date.now();
    const random = Math.floor(Math.random() * 9999);
    return `RITWIK_${timestamp}_${random}`;
}

function generateUPILink(amount, orderId) {
    const params = new URLSearchParams({
        pa: CONFIG.upiId,
        pn: CONFIG.merchantName,
        am: amount.toString(),
        tr: orderId,
        cu: 'INR',
        tn: `Payment to ${CONFIG.businessName}`
    });
    
    return `upi://pay?${params.toString()}`;
}

// Routes

// Health check
app.get('/health', (req, res) => {
    console.log('🔍 Health check requested');
    const health = {
        status: 'OK',
        timestamp: new Date().toISOString(),
        service: 'ritwik-upi-gateway',
        version: '1.0.0',
        config: {
            upiId: CONFIG.upiId,
            merchantName: CONFIG.merchantName,
            paymentsFileExists: fs.existsSync(PAYMENTS_FILE)
        }
    };
    
    res.status(200).json(health);
});

// Serve main page
app.get('/', (req, res) => {
    console.log('📱 Main page requested');
    const indexPath = path.join(__dirname, 'public', 'index.html');
    
    if (fs.existsSync(indexPath)) {
        res.sendFile(indexPath);
    } else {
        res.status(404).send('Index file not found');
    }
});

// Create payment order
app.post('/api/create-order', async (req, res) => {
    console.log('💳 Create order request:', req.body);
    
    try {
        const { amount, customerName, customerEmail } = req.body;
        
        // Validation
        if (!amount || isNaN(amount) || parseFloat(amount) <= 0) {
            console.log('❌ Invalid amount:', amount);
            return res.status(400).json({
                success: false,
                error: 'Please enter a valid amount greater than 0'
            });
        }

        const numericAmount = parseFloat(amount);
        if (numericAmount > 100000) {
            return res.status(400).json({
                success: false,
                error: 'Amount cannot exceed ₹100,000'
            });
        }

        // Generate payment details
        const orderId = generateOrderId();
        const upiLink = generateUPILink(numericAmount, orderId);
        
        console.log(`📝 Generated Order ID: ${orderId}`);
        console.log(`🔗 UPI Link: ${upiLink}`);
        
        // Create payment object
        const payment = {
            orderId,
            amount: numericAmount,
            customerName: customerName || 'Anonymous',
            customerEmail: customerEmail || '',
            upiLink,
            status: 'pending',
            createdAt: new Date().toISOString(),
            expiresAt: new Date(Date.now() + 600000).toISOString(), // 10 minutes
            utr: null,
            verifiedAt: null
        };

        // Save payment
        const payments = loadPayments();
        payments.unshift(payment); // Add to beginning
        
        if (!savePayments(payments)) {
            console.log('❌ Failed to save payment');
            return res.status(500).json({
                success: false,
                error: 'Failed to save payment data'
            });
        }

        console.log('✅ Payment saved successfully');

        // Generate QR Code
        try {
            const qrCodeDataURL = await QRCode.toDataURL(upiLink, {
                width: 300,
                height: 300,
                margin: 2,
                color: {
                    dark: '#000000',
                    light: '#FFFFFF'
                }
            });
            
            console.log('✅ QR Code generated successfully');
            
            const response = {
                success: true,
                orderId,
                amount: numericAmount,
                upiLink,
                qrCode: qrCodeDataURL,
                expiresAt: payment.expiresAt,
                message: 'Payment link and QR code generated successfully!'
            };

            console.log('📤 Sending response:', { ...response, qrCode: 'QR_CODE_DATA' });
            res.json(response);
            
        } catch (qrError) {
            console.error('❌ QR Code generation failed:', qrError);
            
            // Send response without QR code
            const response = {
                success: true,
                orderId,
                amount: numericAmount,
                upiLink,
                qrCode: null,
                expiresAt: payment.expiresAt,
                message: 'Payment link generated (QR code failed to generate)'
            };
            
            res.json(response);
        }

    } catch (error) {
        console.error('❌ Create order error:', error);
        res.status(500).json({
            success: false,
            error: 'Internal server error: ' + error.message
        });
    }
});

// Verify payment
app.post('/api/verify-payment', (req, res) => {
    console.log('🔍 Verify payment request:', req.body);
    
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

        // Check for duplicate UTR
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
        
        if (!savePayments(payments)) {
            return res.status(500).json({
                success: false,
                error: 'Failed to update payment status'
            });
        }

        console.log(`✅ Payment verified: ${orderId}`);

        res.json({
            success: true,
            message: 'Payment verified successfully!',
            status: 'paid',
            orderId,
            amount: payment.amount
        });

    } catch (error) {
        console.error('❌ Verify payment error:', error);
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
                verifiedAt: payment.verifiedAt
            }
        });

    } catch (error) {
        console.error('❌ Payment status error:', error);
        res.status(500).json({
            success: false,
            error: 'Internal server error'
        });
    }
});

// Admin login
app.post('/api/admin/login', (req, res) => {
    console.log('🔐 Admin login attempt:', req.body.username);
    
    const { username, password } = req.body;
    
    if (username === CONFIG.adminUsername && password === CONFIG.adminPassword) {
        console.log('✅ Admin login successful');
        res.json({
            success: true,
            message: 'Login successful'
        });
    } else {
        console.log('❌ Admin login failed');
        res.status(401).json({
            success: false,
            error: 'Invalid username or password'
        });
    }
});

// Get all payments (admin)
app.get('/api/admin/payments', (req, res) => {
    console.log('📊 Admin payments request');
    
    try {
        const payments = loadPayments();
        
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
            payments: payments.slice(0, 100), // Limit to 100 recent payments
            stats
        });
        
    } catch (error) {
        console.error('❌ Admin payments error:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to load payments'
        });
    }
});

// Admin verify payment
app.post('/api/admin/verify-payment', (req, res) => {
    console.log('🔧 Admin verify payment:', req.body);
    
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
        payments[paymentIndex].utr = `ADMIN_${Date.now()}`;
        
        if (!savePayments(payments)) {
            return res.status(500).json({
                success: false,
                error: 'Failed to update payment'
            });
        }

        console.log(`✅ Admin verified payment: ${orderId}`);

        res.json({
            success: true,
            message: 'Payment marked as verified'
        });

    } catch (error) {
        console.error('❌ Admin verify error:', error);
        res.status(500).json({
            success: false,
            error: 'Internal server error'
        });
    }
});

// Success page
app.get('/success', (req, res) => {
    const orderId = req.query.order;
    res.send(`
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Payment Successful - Ritwik's UPI Gateway</title>
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
                .success-container { 
                    background: white; 
                    padding: 50px; 
                    border-radius: 20px; 
                    box-shadow: 0 25px 50px rgba(0,0,0,0.15); 
                    text-align: center; 
                    max-width: 600px; 
                    width: 100%; 
                    animation: slideUp 0.6s ease-out;
                }
                @keyframes slideUp {
                    from { opacity: 0; transform: translateY(50px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                .success-icon { 
                    font-size: 100px; 
                    color: #28a745; 
                    margin-bottom: 30px; 
                    animation: bounce 2s infinite;
                }
                @keyframes bounce {
                    0%, 20%, 50%, 80%, 100% { transform: translateY(0); }
                    40% { transform: translateY(-10px); }
                    60% { transform: translateY(-5px); }
                }
                h1 { 
                    color: #28a745; 
                    margin-bottom: 20px; 
                    font-size: 32px;
                }
                .order-info { 
                    background: #f8f9fa; 
                    padding: 25px; 
                    border-radius: 15px; 
                    margin: 25px 0; 
                    font-family: 'Courier New', monospace; 
                    font-size: 18px;
                    border-left: 5px solid #28a745;
                }
                .back-btn { 
                    background: linear-gradient(135deg, #007bff, #0056b3); 
                    color: white; 
                    padding: 15px 30px; 
                    border: none; 
                    border-radius: 10px; 
                    text-decoration: none; 
                    display: inline-block; 
                    margin-top: 25px; 
                    font-size: 16px;
                    font-weight: 600;
                    transition: all 0.3s ease; 
                }
                .back-btn:hover { 
                    transform: translateY(-3px); 
                    box-shadow: 0 10px 25px rgba(0,123,255,0.3);
                }
                p { font-size: 18px; color: #555; line-height: 1.6; }
            </style>
        </head>
        <body>
            <div class="success-container">
                <div class="success-icon">✅</div>
                <h1>Payment Successful!</h1>
                <p>Your payment has been processed and verified successfully.</p>
                ${orderId ? `<div class="order-info">Order ID: ${orderId}</div>` : ''}
                <p>Thank you for choosing <strong>${CONFIG.businessName}</strong>!</p>
                <a href="/" class="back-btn">← Back to Payment Gateway</a>
            </div>
        </body>
        </html>
    `);
});

// Error handling
app.use((err, req, res, next) => {
    console.error('💥 Unhandled error:', err);
    res.status(500).json({
        success: false,
        error: 'Something went wrong on our end!'
    });
});

// 404 handler
app.use((req, res) => {
    console.log('❓ 404 - Route not found:', req.url);
    res.status(404).json({
        success: false,
        error: 'Route not found'
    });
});

// Start server
app.listen(PORT, '0.0.0.0', () => {
    console.log('🚀 ===================================');
    console.log(`🚀 Ritwik's UPI Gateway STARTED!`);
    console.log(`🚀 Port: ${PORT}`);
    console.log(`🚀 Environment: ${process.env.NODE_ENV || 'development'}`);
    console.log(`🚀 UPI ID: ${CONFIG.upiId}`);
    console.log(`🚀 Merchant: ${CONFIG.merchantName}`);
    console.log(`🚀 Admin User: ${CONFIG.adminUsername}`);
    console.log(`🚀 Admin Pass: ${CONFIG.adminPassword}`);
    console.log(`🚀 Main Site: http://localhost:${PORT}`);
    console.log(`🚀 Admin Panel: http://localhost:${PORT}/admin.html`);
    console.log('🚀 ===================================');
});
