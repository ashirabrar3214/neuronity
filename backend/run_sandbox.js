const { loadPyodide } = require('pyodide');
const fs = require('fs');

async function run() {
    const args = process.argv.slice(2);
    if (args.length < 1) {
        console.error("Usage: node run_sandbox.js <python_file_path> [input_data]");
        process.exit(1);
    }

    const pyFilePath = args[0];
    const inputData = args.length > 1 ? args[1] : "";
    const workingDir = args.length > 2 ? args[2] : "";

    let pyCode;
    try {
        pyCode = fs.readFileSync(pyFilePath, 'utf8');
    } catch (e) {
        console.error(`Error reading ${pyFilePath}: ${e.message}`);
        process.exit(1);
    }

    try {
        // Initialize Pyodide
        const pyodide = await loadPyodide();

        // Security: Remove dangerous built-in modules so the agent script cannot import them
        await pyodide.runPythonAsync(`
import sys
if 'subprocess' in sys.modules: del sys.modules['subprocess']
if 'shutil' in sys.modules: del sys.modules['shutil']
if 'socket' in sys.modules: del sys.modules['socket']
sys.modules['subprocess'] = None
sys.modules['shutil'] = None
sys.modules['socket'] = None
        `);

        // Redirect Python stdout and stderr to Node console
        pyodide.setStdout({ batched: (str) => console.log(str) });
        pyodide.setStderr({ batched: (str) => console.error(str) });

        // Load core packages if needed in the future (e.g. pyodide.loadPackage('micropip'))

        // Mount the working directory if provided
        if (workingDir && fs.existsSync(workingDir)) {
            pyodide.FS.mkdir('/workspace');
            pyodide.FS.mount(pyodide.FS.filesystems.NODEFS, { root: workingDir }, '/workspace');

            // Change directory to the workspace so relative paths work automatically
            await pyodide.runPythonAsync(`
import os
os.chdir('/workspace')
            `);
        }

        // We inject the input data into the global namespace
        // We do this AFTER potential imports but BEFORE the main code runs
        pyodide.globals.set("TOOL_INPUT", inputData);

        console.log("--- [SANDBOX] Execution Started ---");

        // Run the code
        const result = await pyodide.runPythonAsync(pyCode);

        console.log("--- [SANDBOX] Execution Finished ---");

        // Print the result to stdout for the Python backend to capture
        if (result !== undefined && result !== null) {
            console.log(result.toString());
        }

    } catch (e) {
        // Pyodide Python errors will be caught here
        console.error(e.toString());
        process.exit(1);
    }
}

run();
