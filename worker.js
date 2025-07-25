// worker.js - Background auto-verification worker
const fs = require('fs');
const path = require('path');
const moment = require('moment');

const DATA_DIR = process.env.DATA_DIR || path.join(__dirname, 'data');
const PAYMENTS_FILE = path.join(DATA_DIR, 'payments.json');
const WORKER_LOG = path.join(DATA_DIR, 'worker.log');

function loadPayments() {
    try {
        const data = fs.readFileSync(PAYMENTS_FILE, 'utf8');
        return JSON.parse(data);
    } catch (error) {
        return [];
    }
}

function savePayments(payments) {
    try {
        fs.writeFileSync(PAYMENTS_FILE, JSON.stringify(payments, null, 2));
        return true;
    } catch (error) {
        return false;
    }
}

function logWorker(message, data = {}) {
    const logEntry = {
        timestamp: moment().toISOString(),
        service: 'payment-verifier',
        message,
        data
    };
    
    console.log(JSON.stringify(logEntry));
    
    try {
        fs.appendFileSync(WORKER_LOG, JSON.stringify(logEntry) + '\n');
    } catch (error) {
        console.error('Worker log write failed:', error);
    }
}

function processAutoVerification() {
    try {
        const payments = loadPayments();
        let updatedCount = 0;
        
        payments.forEach(payment => {
            // Auto-verify pending payments older than 2 minutes (simulation)
            if (payment.status === 'pending' && 
                moment().diff(moment(payment.createdAt), 'minutes') >= 2 &&
                Math.random() > 0.6) { // 40% chance to simulate real verification
                
                payment.status = 'paid';
                payment.verifiedAt = moment().toISOString();
                payment.verificationMethod = 'auto-worker';
                payment.utr = `WORKER_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                
                updatedCount++;
                
                logWorker('Payment auto-verified', {
                    orderId: payment.orderId,
                    amount: payment.amount,
                    utr: payment.utr
                });
            }
        });
        
        if (updatedCount > 0) {
            savePayments(payments);
            logWorker('Auto-verification batch completed', { updated: updatedCount });
        }
        
    } catch (error) {
        logWorker('Auto-verification error', { error: error.message });
    }
}

// Run verification every 30 seconds
setInterval(processAutoVerification, 30000);

logWorker('Payment verification worker started');
console.log('🔄 Payment Verification Worker Started');
