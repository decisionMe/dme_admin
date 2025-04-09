# DME Admin

A simple administrative interface for managing DecisionMe prompts.

## Setup Instructions

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd dme_admin
   ```

2. **Create and activate a virtual environment (optional but recommended)**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp example.env .env
   ```
   
   Open the `.env` file and update the values:
   - `ADMIN_PASSWORD`: Set a secure password for the admin interface
   - `DATABASE_URL`: Set the connection string for your database (should match the main DecisionMe application database)

5. **Run the application**
   ```bash
   uvicorn app:app --reload
   ```

6. **Access the admin interface**
   
   Open your browser and navigate to [http://localhost:8000](http://localhost:8000)
   
   You will be prompted to enter the admin password that you configured in the `.env` file.

## Features

- Secure admin login with password protection
- View and manage all prompts in the DecisionMe database
- Add new prompts with name, notes, and prompt content
- Edit existing prompts with proper formatting
- Simple, clean interface focused on prompt management

## Maintenance

- The application connects directly to the DecisionMe database
- No database migrations are needed as it uses the existing schema
- Ensure your database connection string is updated if the database location changes