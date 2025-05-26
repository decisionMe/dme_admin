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
- Subscription validation settings management
- Comprehensive monitoring dashboard for subscription events
- Real-time alerts for API failures and validation spikes

## Database Management

**IMPORTANT**: This project shares a database with the d-me project. All database migrations must be created and run from the d-me project.

### Adding New Database Fields

If you need to add new fields to models (e.g., GlobalConfig):

1. Add the fields to the model in this project (dme_admin)
2. Switch to the d-me project to create and run the migration:
   ```bash
   cd ../d-me
   alembic revision --autogenerate -m "description of changes"
   alembic upgrade head
   ```

### DO NOT:
- Install or initialize Alembic in this project
- Create migrations in this project
- Run `alembic upgrade` from this project

## Monitoring

The admin interface includes a comprehensive monitoring dashboard for subscription validation:

### Dashboard Features
- **Real-time Metrics**: View validation success rates, API health, and user redirects
- **Timeline Charts**: Visualize trends over 24 hours, 7 days, or 30 days
- **Alert System**: Automatic alerts for:
  - Stripe API failure rates above 10%
  - Validation check spikes (2x normal rate)
- **Recent Failures**: Detailed view of recent failed validations and API errors

### Accessing Monitoring
1. Navigate to `/admin/monitoring` or click "Monitoring" from the prompts page
2. Use the period selector to view different time ranges
3. Alerts appear automatically when thresholds are exceeded

## Maintenance

- The application connects directly to the DecisionMe database
- Database schema changes must be made through the d-me project
- Ensure your database connection string is updated if the database location changes
- Monitor the `/admin/monitoring` dashboard regularly for subscription system health