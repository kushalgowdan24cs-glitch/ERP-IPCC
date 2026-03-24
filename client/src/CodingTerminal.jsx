import React, { useState, useEffect, useRef } from 'react';
import Editor from '@monaco-editor/react';

const DEFAULT_CODE = `def solve(input_str):
    # Write your logic here
    # Example: return the string in uppercase
    return input_str.upper()

# --- SYSTEM CODE: DO NOT MODIFY ---
import sys
import js
if __name__ == '__main__':
    # Read from our secure javascript-injected stdin
    print(solve(js.current_stdin))`;

export default function CodingTerminal({ question, onPassAll }) {
  const [code, setCode] = useState(DEFAULT_CODE);
  const [results, setResults] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isEngineReady, setIsEngineReady] = useState(false);

  // Reference to the in-browser Python engine
  const pyodideRef = useRef(null);

  // 1. Boot the Python engine on load
  useEffect(() => {
    const loadEngine = async () => {
      try {
        if (window.loadPyodide) {
          pyodideRef.current = await window.loadPyodide();
          setIsEngineReady(true);
          console.log('Pyodide WASM engine loaded locally');
          return;
        }

        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/pyodide/v0.25.0/full/pyodide.js';
        script.onload = async () => {
          pyodideRef.current = await window.loadPyodide();
          setIsEngineReady(true);
          console.log('Pyodide WASM engine loaded locally');
        };
        document.body.appendChild(script);
      } catch (e) {
        console.error('Failed to load engine', e);
      }
    };
    loadEngine();
  }, []);

  const runCode = async () => {
    if (!isEngineReady || !pyodideRef.current) return;

    setIsRunning(true);
    setResults([]);
    const newResults = [];
    let allPassed = true;

    // 2. Run all test cases locally
    for (let i = 0; i < question.testCases.length; i++) {
      const tc = question.testCases[i];
      let actualOutput = '';
      let errorMsg = null;

      try {
        // Inject the hidden test case input into global JS scope
        window.current_stdin = tc.input;

        // Hijack stdout so Python print() can be read by JS
        pyodideRef.current.runPython(`
import sys
import io
sys.stdout = io.StringIO()
`);

        // Execute student code
        await pyodideRef.current.runPythonAsync(code);

        // Retrieve captured output
        actualOutput = pyodideRef.current.runPython('sys.stdout.getvalue()').trim();
      } catch (err) {
        errorMsg = err.message;
        allPassed = false;
      }

      const expectedOutput = tc.expected.trim();
      const passed = !errorMsg && actualOutput === expectedOutput;

      if (!passed) allPassed = false;

      newResults.push({
        id: i + 1,
        status: passed ? 'Passed' : errorMsg ? 'Compiler Error' : 'Failed',
        output: actualOutput,
        expected: expectedOutput,
        error: errorMsg,
        passed,
      });
    }

    setResults(newResults);
    setIsRunning(false);

    if (allPassed && newResults.length > 0) {
      setTimeout(() => onPassAll(), 1500);
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div style={{ display: 'flex', gap: '15px', alignItems: 'center' }}>
          <span style={{ color: '#94a3b8', fontWeight: 'bold' }}>Terminal:</span>
          <span
            style={{
              background: '#1e293b',
              padding: '6px 12px',
              borderRadius: '6px',
              color: '#38bdf8',
              fontWeight: 'bold',
              border: '1px solid #334155',
            }}
          >
            Python 3 (Local WASM)
          </span>
        </div>

        <button
          onClick={runCode}
          disabled={isRunning || !isEngineReady}
          style={isRunning || !isEngineReady ? styles.runBtnDisabled : styles.runBtn}
        >
          {!isEngineReady ? 'Loading Engine...' : isRunning ? 'Executing...' : 'Run All Tests'}
        </button>
      </div>

      <div style={styles.editorWrapper}>
        <Editor
          height="100%"
          language="python"
          theme="vs-dark"
          value={code}
          onChange={(val) => setCode(val || '')}
          options={{ minimap: { enabled: false }, fontSize: 16, padding: { top: 15 } }}
        />
      </div>

      <div style={styles.resultsWrapper}>
        <h4 style={{ margin: '0 0 15px 0', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '10px' }}>
          Execution Results
          {results.length > 0 && (
            <span style={{ background: '#e2e8f0', padding: '4px 10px', borderRadius: '12px', fontSize: '13px' }}>
              {results.filter((r) => r.passed).length} / {question.testCases.length} Passed
            </span>
          )}
        </h4>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {results.map((res, idx) => (
            <div
              key={idx}
              style={{
                ...styles.testCard,
                borderColor: res.passed ? '#10b981' : '#ef4444',
                backgroundColor: res.passed ? '#ecfdf5' : '#fef2f2',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontWeight: 'bold',
                  color: res.passed ? '#047857' : '#b91c1c',
                }}
              >
                <span>Test Case {res.id}</span>
                <span>{res.status}</span>
              </div>

              {!res.passed && !res.error && (
                <div style={{ marginTop: '10px', display: 'flex', gap: '10px' }}>
                  <div style={{ flex: 1 }}>
                    <div style={styles.label}>Your Output:</div>
                    <div style={styles.outputBox}>{res.output || '<empty>'}</div>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={styles.label}>Expected:</div>
                    <div style={styles.outputBox}>{res.expected}</div>
                  </div>
                </div>
              )}

              {!res.passed && res.error && (
                <div style={{ ...styles.outputBox, color: '#ef4444', marginTop: '10px' }}>{res.error}</div>
              )}
            </div>
          ))}

          {results.length === 0 && (
            <div
              style={{
                textAlign: 'center',
                color: '#64748b',
                padding: '30px',
                border: '2px dashed #cbd5e1',
                borderRadius: '12px',
              }}
            >
              Write your code and run tests locally with zero server lag.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    background: 'white',
    borderRadius: '12px',
    border: '1px solid #cbd5e1',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px 20px',
    background: '#0f172a',
  },
  runBtn: {
    background: '#10b981',
    color: 'white',
    padding: '8px 20px',
    borderRadius: '8px',
    border: 'none',
    fontWeight: 'bold',
    cursor: 'pointer',
  },
  runBtnDisabled: {
    background: '#475569',
    color: '#94a3b8',
    padding: '8px 20px',
    borderRadius: '8px',
    border: 'none',
    fontWeight: 'bold',
  },
  editorWrapper: {
    height: '350px',
    backgroundColor: '#1e1e1e',
    borderBottom: '1px solid #cbd5e1',
  },
  resultsWrapper: {
    padding: '20px',
    flex: 1,
    overflowY: 'auto',
    backgroundColor: '#f8fafc',
  },
  testCard: {
    padding: '15px',
    borderRadius: '10px',
    borderLeft: '5px solid',
  },
  label: {
    fontSize: '12px',
    color: '#64748b',
    fontWeight: 'bold',
    marginBottom: '4px',
    textTransform: 'uppercase',
  },
  outputBox: {
    background: 'white',
    padding: '10px',
    borderRadius: '6px',
    fontFamily: 'monospace',
    fontSize: '13px',
    border: '1px solid #e2e8f0',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-all',
  },
};
