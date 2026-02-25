# Plan: Python-Native Research Demo (Streamlit)

We will build a pure Python frontend using **Streamlit**. This approach is ideal for scientific research demos as it allows for rapid iteration, native data visualization, and keeps the entire stack (Frontend + Backend) in Python.

## Tech Stack
-   **Framework**: Streamlit (Standard for ML/Data Science demos).
-   **Communication**: `requests` (to communicate with the `reading_concierge` FastAPI backend).
-   **Visualization**: `pandas` (for metrics) and Streamlit's native components.

## 1. Project Initialization
-   [ ] Remove the `frontend/` (Node.js) directory.
-   [ ] Add `demo_app/` directory.
-   [ ] Update `requirements.txt` to include `streamlit`.

## 2. Core Components
-   **Sidebar Controls**:
    -   Configuration for Scenario (Cold/Warm), Top-K, and Validation Strictness.
    -   JSON editors for `User Profile` and `History` (for research adaptability).
-   **Chat Interface**:
    -   Streamlit `st.chat_message` interface for a natural conversation flow.
-   **Result Visualization**:
    -   Expandable containers for each book recommendation.
    -   Rich text display for "Why this book?" explanations.
    -   Metrics display (Novelty, Diversity) using `st.metric`.
-   **Debug Inspector**:
    -   `st.expander` containing the raw JSON response from the orchestration agents.

## 3. Implementation Steps
1.  **Setup**: Install Streamlit.
2.  **State Management**: Use `st.session_state` to store conversation history and config.
3.  **API Client**: Write a helper function to send blocking requests to `http://localhost:8100/user_api`.
4.  **Layout**:
    -   **Left**: Sidebar with settings.
    -   **Center**: Chat input and results area.
    -   **Bottom**: Benchmark summary status (from `/demo/benchmark-summary`).
5.  **Execution**: Run via `streamlit run demo_app/app.py`.

## 4. Verification
-   **Backend**: Ensure `reading_concierge` is running (`python -m reading_concierge.reading_concierge`).
-   **Frontend**: Run `streamlit run demo_app/app.py`.
-   **Interaction**: Send a query and verify the logic flow and response rendering.

## Advantages for Research
-   **No Context Switching**: Developers stay in Python.
-   **Introspection**: Easy to debug dataframes and agent states.
-   **Portability**: Easy to package and share with other researchers.

