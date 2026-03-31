const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn, exec } = require('child_process');

const PORT = 3000;

const MIME_TYPES = {
    '.html': 'text/html',
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
};

// Start Python backend
const scriptPath = path.join(__dirname, 'backend', 'interpreter.py');
const pythonProcess = spawn('python', [scriptPath], {
    env: { ...process.env, PYTHONUTF8: '1' }
});

pythonProcess.stdout.on('data', (data) => {
    console.log(`Python: ${data.toString().trim()}`);
});

pythonProcess.stderr.on('data', (data) => {
    const str = data.toString();
    if (str.includes('INFO:') || str.includes('WARNING:')) {
        console.log(`Python backend: ${str.trim()}`);
    } else {
        console.error(`Python backend Error: ${str.trim()}`);
    }
});

pythonProcess.on('close', (code) => {
    console.log(`Python backend exited with code ${code}`);
});

// Serve static files
const server = http.createServer((req, res) => {
    let filePath = req.url === '/' ? '/canvas.html' : req.url;
    // Strip query strings and decode URI
    filePath = decodeURIComponent(filePath.split('?')[0]);
    const fullPath = path.resolve(path.join(__dirname, filePath));

    // Security: prevent directory traversal
    if (!fullPath.startsWith(__dirname)) {
        res.writeHead(403);
        res.end('Forbidden');
        return;
    }

    const ext = path.extname(fullPath);
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';

    fs.readFile(fullPath, (err, data) => {
        if (err) {
            res.writeHead(404);
            res.end('Not Found');
            return;
        }
        res.writeHead(200, { 'Content-Type': contentType });
        res.end(data);
    });
});

server.listen(PORT, () => {
    const url = `http://localhost:${PORT}`;
    console.log(`Easy Company running at ${url}`);
    // Auto-open in default browser
    const start = process.platform === 'win32' ? 'start' : process.platform === 'darwin' ? 'open' : 'xdg-open';
    exec(`${start} ${url}`);
});

// Cleanup on exit
process.on('SIGINT', () => {
    pythonProcess.kill();
    process.exit();
});

process.on('SIGTERM', () => {
    pythonProcess.kill();
    process.exit();
});
