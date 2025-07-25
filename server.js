const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const fs = require('fs');
const path = require('path');
const QRCode = require('qrcode');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));
app.use(express.static('public'));

// Configuration
const CONFIG = {
    upiId: '7477772650@ibl',
    merchantName: 'YourShop',
    adminUsername: 'admin',
    adminPassword: 'admin123'
};

// Data file path
const PAYMENTS_FILE = 'payments.json';

// Initialize payments file if not exists
if (!fs.existsSync(PAYMENTS_FILE)) {
    fs.writeFileSync(PAYMENTS_FILE, JSON.stringify([], null, 2));
}

// Helper functions
function loadPayments() {
    try {
        const data = fs.readFileSync(PAYMENTS_FILE, 'utf8');
        return JSON.parse(data);
    } catch (error) {
        return [];
    }
}

function savePayments(payments) {
    fs.writeFileSync(PAYMENTS_FILE, JSON.stringify(payments, null, 2));
}

function generateOrderId() {
    const now = new Date();
    const timestamp = now.toISOString().replace(/[-:T.]/g, '').slice(0, 14);
    const random = Math.floor(Math.random() * 1000).toString().padStart(3, '0');
    return `ORD_${timestamp}_${random}`;
}

function generateUPILink(amount, orderId) {
    return `upi://pay?pa=${CONFIG.upiId}&pn=${CONFIG.merchantName}&am=${amount}&tr=${orderId}&cu=INR`;
}

// Routes

// Home page
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Create new payment order
app.post('/api/create-order', (req, res) => {
    try {
        const { amount, customerName, customerEmail } = req.body;
        
        if (!amount || amount <= 0) {
            return res.status(400).json({ error: 'Invalid amount' });
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
            utr: null,
            verifiedAt: null
        };

        const payments = loadPayments();
        payments.push(payment);
        savePayments(payments);

        // Generate QR Code
        QRCode.toDataURL(upiLink, (err, qrCode) => {
            if (err) {
                console.error('QR Code generation error:', err);
                return res.json({
                    success: true,
                    orderId,
                    amount,
                    upiLink,
                    qrCode: null
                });
            }

            res.json({
                success: true,
                orderId,
                amount,
                upiLink,
                qrCode
            });
        });

    } catch (error) {
        console.error('Error creating order:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Verify payment
app.post('/api/verify-payment', (req, res) => {
    try {
        const { orderId, utr } = req.body;
        
        if (!orderId || !utr) {
            return res.status(400).json({ error: 'Order ID and UTR are required' });
        }

        const payments = loadPayments();
        const paymentIndex = payments.findIndex(p => p.orderId === orderId);
        
        if (paymentIndex === -1) {
            return res.status(404).json({ error: 'Order not found' });
        }

        const payment = payments[paymentIndex];
        
        if (payment.status === 'paid') {
            return res.json({ 
                success: false, 
                message: 'Payment already verified',
                status: 'paid'
            });
        }

        // Check if UTR already exists (duplicate protection)
        const existingUTR = payments.find(p => p.utr === utr && p.utr !== null);
        if (existingUTR) {
            return res.status(400).json({ error: 'This UTR has already been used' });
        }

        // Simulate auto verification (in real scenario, you'd match with bank SMS/webhook)
        // For demo, we'll mark as verified if UTR is provided
        payments[paymentIndex].utr = utr;
        payments[paymentIndex].status = 'paid';
        payments[paymentIndex].verifiedAt = new Date().toISOString();
        
        savePayments(payments);

        res.json({
            success: true,
            message: 'Payment verified successfully',
            status: 'paid',
            orderId,
            amount: payment.amount
        });

    } catch (error) {
        console.error('Error verifying payment:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Get payment status
app.get('/api/payment-status/:orderId', (req, res) => {
    try {
        const { orderId } = req.params;
        const payments = loadPayments();
        const payment = payments.find(p => p.orderId === orderId);
        
        if (!payment) {
            return res.status(404).json({ error: 'Order not found' });
        }

        res.json({
            success: true,
            payment: {
                orderId: payment.orderId,
                amount: payment.amount,
                status: payment.status,
                createdAt: payment.createdAt,
                verifiedAt: payment.verifiedAt
            }
        });

    } catch (error) {
        console.error('Error getting payment status:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Admin login
app.post('/api/admin/login', (req, res) => {
    const { username, password } = req.body;
    
    if (username === CONFIG.adminUsername && password === CONFIG.adminPassword) {
        res.json({ success: true, message: 'Login successful' });
    } else {
        res.status(401).json({ error: 'Invalid credentials' });
    }
});

// Get all payments (admin)
app.get('/api/admin/payments', (req, res) => {
    try {
        const payments = loadPayments();
        res.json({ success: true, payments });
    } catch (error) {
        console.error('Error getting payments:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Manually verify payment (admin)
app.post('/api/admin/verify-payment', (req, res) => {
    try {
        const { orderId } = req.body;
        const payments = loadPayments();
        const paymentIndex = payments.findIndex(p => p.orderId === orderId);
        
        if (paymentIndex === -1) {
            return res.status(404).json({ error: 'Order not found' });
        }

        payments[paymentIndex].status = 'paid';
        payments[paymentIndex].verifiedAt = new Date().toISOString();
        
        savePayments(payments);

        res.json({ success: true, message: 'Payment marked as verified' });

    } catch (error) {
        console.error('Error verifying payment:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Webhook endpoint (for future PG integration)
app.post('/api/webhook', (req, res) => {
    console.log('Webhook received:', req.body);
    // Process webhook data here
    res.json({ success: true });
});

// Start server
app.listen(PORT, () => {
    console.log(`UPI Payment Gateway server running on port ${PORT}`);
    console.log(`Access the application at: http://localhost:${PORT}`);
    console.log(`Admin panel at: http://localhost:${PORT}/admin.html`);
});
                                         
