const fs = require('fs');
const path = require('path');

const distDir = path.join(__dirname, 'dist');
if (!fs.existsSync(distDir)) {
    fs.mkdirSync(distDir);
}

const filesToCopy = [
    'index.html',
    'canvas.html',
    'style.css',
    'canvas.css',
    'agent-training.css',
    'canvas.js',
    'agent-training.js',
    'renderer.js'
];

filesToCopy.forEach(file => {
    if (fs.existsSync(file)) {
        fs.copyFileSync(file, path.join(distDir, file));
        console.log(`Copied ${file} to dist/`);
    } else {
        console.warn(`Warning: ${file} not found.`);
    }
});

console.log('Build complete.');
