# Contributing to AutoTest

Thank you for your interest in contributing to **AutoTest**! We welcome contributions from developers of all skill levels.

---

## 🛠️ Prerequisites

Before you start, make sure you have the following installed:

- **Python 3.11+** (Python 3.11 or 3.12 recommended)
- **Node.js 18+** & **npm** (for the React/Vite frontend)
- **Git**

---

## 🚀 Development Setup

### 1. Clone the Repository

```bash
git clone https://github.com/nourelhoudadarghoumii/multi-agent-testing.git
cd multi-agent-testing
```

### 2. Backend Setup (Python)

```bash
# Create and activate a virtual environment
python -m venv venv

# On Linux/macOS:
source venv/bin/activate

# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# On Windows (CMD):
.\venv\Scripts\activate.bat

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration

```bash
cp .env.example .env
```

Open `.env` and configure your keys:
- `OPENROUTER_API_KEY`: Required for LLM test generation & debugging ([Get a key](https://openrouter.ai/keys)).
- `E2B_API_KEY`: Optional, for remote sandboxed execution ([Get a key](https://e2b.dev/)).

> **IMPORTANT:** Never commit `.env` or real API keys to Git.

### 4. Frontend Setup (React / Vite)

```bash
cd frontend
npm install
npm run dev
```

The frontend will run at `http://localhost:5173`.

### 5. Running the Backend Server

```bash
# From the project root
uvicorn api.main:app --reload --port 8000
```

The FastAPI docs will be available at `http://localhost:8000/docs`.

---

## 🧪 Running Tests

Always ensure the full test suite passes before submitting changes:

```bash
# Run all unit tests
pytest

# Run tests with coverage report
pytest --cov=agents --cov=core --cov=api

# Run frontend build check
cd frontend && npm run build
```

---

## 🌿 Contribution Workflow

1. **Fork the repository** on GitHub.
2. **Create a topic branch**:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-description
   ```
3. **Commit your changes**:
   - Write clear, imperative commit messages (`feat: add AST support for Walrus operator`, `fix: handle edge case in executor timeout`).
4. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```
5. **Open a Pull Request** against the `main` branch with a clear description of your changes and test coverage.

---

## 🔒 Security Vulnerabilities

If you discover a security vulnerability, please do **NOT** open a public issue. Instead, report it privately to the maintainers or via GitHub Security Advisories.

---

## 📄 License

By contributing to AutoTest, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).
