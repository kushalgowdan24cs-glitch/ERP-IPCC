import React, { useState, useEffect, useRef } from 'react';

export default function ExamView({ exam, onAnswer, onComplete, onExamStart }) {
  const [currentQ, setCurrentQ] = useState(0);
  const [answers, setAnswers] = useState({});
  const [started, setStarted] = useState(false);
  const [timeLeft, setTimeLeft] = useState((exam?.duration_minutes || 60) * 60);

  const questions = exam?.questions || [];

  // Start exam timer
  useEffect(() => {
    if (!started) return;
    const timer = setInterval(() => {
      setTimeLeft(prev => {
        if (prev <= 1) {
          clearInterval(timer);
          handleSubmit();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [started]);

  // Start exam on first render
  useEffect(() => {
    if (!started) {
      setStarted(true);
      onExamStart();
    }
  }, []);

  const formatTime = (seconds) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const handleSelectOption = (optionIndex) => {
    const newAnswers = { ...answers, [currentQ]: optionIndex };
    setAnswers(newAnswers);
    onAnswer(currentQ, String(optionIndex));
  };

  const handleTextAnswer = (text) => {
    const newAnswers = { ...answers, [currentQ]: text };
    setAnswers(newAnswers);
    onAnswer(currentQ, text);
  };

  const handleNext = () => {
    if (currentQ < questions.length - 1) {
      setCurrentQ(currentQ + 1);
    }
  };

  const handleSubmit = () => {
    onComplete();
  };

  if (questions.length === 0) {
    return <div className="card"><h1>No questions loaded</h1></div>;
  }

  const q = questions[currentQ];
  const isLast = currentQ === questions.length - 1;

  return (
    <div className="exam-container">
      <div className="question-card">
        <div className="question-header">
          <span className="question-number">
            Question {currentQ + 1} of {questions.length}
          </span>
          <span style={{
            fontSize: '1.1rem',
            fontWeight: 700,
            color: timeLeft < 300 ? 'var(--danger)' : 'var(--text-primary)',
          }}>
            ⏱️ {formatTime(timeLeft)}
          </span>
          <span className="question-type">
            {q.type === 'mcq' ? 'Multiple Choice' : 'Short Answer'}
          </span>
        </div>

        <div className="question-text">{q.text}</div>

        {q.type === 'mcq' ? (
          <ul className="options-list">
            {q.options.map((option, idx) => (
              <li
                key={idx}
                className={`option-item ${answers[currentQ] === idx ? 'selected' : ''}`}
                onClick={() => handleSelectOption(idx)}
              >
                <span className="option-letter">
                  {String.fromCharCode(65 + idx)}
                </span>
                <span>{option}</span>
              </li>
            ))}
          </ul>
        ) : (
          <textarea
            className="short-answer-input"
            placeholder="Type your answer here..."
            value={answers[currentQ] || ''}
            onChange={(e) => handleTextAnswer(e.target.value)}
            onPaste={(e) => {
              e.preventDefault(); // Block paste
              if (window.proctorAPI) {
                // This is handled by Electron shortcuts, but also block here
              }
            }}
          />
        )}

        <div className="question-nav">
          {isLast ? (
            <button className="btn btn-success" onClick={handleSubmit}>
              ✅ Submit Exam
            </button>
          ) : (
            <button
              className="btn btn-primary"
              onClick={handleNext}
              disabled={answers[currentQ] === undefined}
            >
              Next Question →
            </button>
          )}
        </div>
      </div>
    </div>
  );
}