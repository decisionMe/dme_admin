# Subscription Flow Documentation

## Overview
This document outlines the complete subscription flow between the DME Admin application and the client application (d-me), including database models, data flow, and integration points.

## Architecture Overview

### Applications
- **DME Admin** (`dme_admin`): Handles Stripe payments, user registration, and Auth0 integration
- **Client App** (`d-me`): Main application with subscription validation middleware

### Shared Database
Both applications share the same database with two key tables:
- `subscription_users`: Managed by DME Admin for auth flow
- `subscriptions`: Used by client app for subscription validation

## Database Models

### SubscriptionUser Table (DME Admin)
**Purpose**: Track the auth/registration flow for new subscribers

```python
class SubscriptionUser(Base):
    __tablename__ = "subscription_users"
    
    subscription_id = Column(String, primary_key=True, index=True)  # Stripe subscription ID
    email = Column(String, nullable=True)
    purchaser_email = Column(String, nullable=True)
    auth0_id = Column(String, nullable=True, index=True)
    registration_status = Column(Enum("PAYMENT_COMPLETED", "AUTH0_INVITE_SENT", "AUTH0_ACCOUNT_LINKED"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
```

### Subscriptions Table (Client App)
**Purpose**: Store subscription data for client app validation

```python
class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"))  # This is the auth0_id
    payment_method = Column(String)  # THIS CONTAINS THE STRIPE SUBSCRIPTION ID
    status = Column(String)  # active, canceled, expired, etc.
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))  # Expiry date from Stripe current_period_end
    payment_status = Column(String)
    next_payment_date = Column(DateTime(timezone=True))
    auto_renew = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
```

**Key Point**: `payment_method` field contains the Stripe subscription ID, NOT a payment method ID.

## Subscription Flows

### 1. Normal Purchase Flow

#### Step 1: Stripe Checkout
1. User completes Stripe checkout
2. DME Admin receives success callback with `session_id`
3. Retrieves Stripe session and subscription details

#### Step 2: Create SubscriptionUser Record
```python
# routes/subscription.py - Stripe success handler
user = SubscriptionUser(
    subscription_id=subscription_id,  # From Stripe
    email=customer_email,
    purchaser_email=customer_email,
    registration_status="PAYMENT_COMPLETED"
)
db.merge(user)
```

#### Step 3: Auth0 Registration
1. User is redirected to Auth0 for account creation
2. Auth0 callback triggers with authorization code
3. DME Admin exchanges code for tokens and gets `auth0_id`

#### Step 4: Create Subscription Record
```python
# auth0_subscription_handler.py - Auth0 callback
subscription_record = Subscription(
    user_id=user_info["sub"],  # auth0_id
    payment_method=subscription_id,  # Stripe subscription ID
    status=subscription.status,
    start_date=datetime.fromtimestamp(subscription.start_date),
    end_date=datetime.fromtimestamp(subscription.current_period_end),  # Expiry date
    payment_status='paid',
    auto_renew=True
)
db.merge(subscription_record)
```

#### Step 5: Update Registration Status
```python
user.auth0_id = user_info["sub"]
user.registration_status = "AUTH0_ACCOUNT_LINKED"
```

### 2. Gift Subscription Flow

#### Steps 1-2: Same as Normal Flow
- Stripe checkout completes
- SubscriptionUser record created with purchaser's email

#### Step 3: Gift Processing
```python
# Different user email provided in checkout
user = SubscriptionUser(
    subscription_id=subscription_id,
    email=recipient_email,  # Gift recipient
    purchaser_email=customer_email,  # Actual purchaser
    registration_status="PAYMENT_COMPLETED"
)
```

#### Step 4: Auth0 Invitation
1. Auth0 invitation sent to recipient email
2. Status updated to "AUTH0_INVITE_SENT"

#### Steps 5-6: Same as Normal Flow
- Recipient creates Auth0 account
- Subscription record created with recipient's `auth0_id`

### 3. Admin Recovery Flow

#### Step 1: Admin Creates Recovery
```python
# routes/subscription.py - Admin recovery endpoint
user = SubscriptionUser(
    subscription_id=request.subscription_id,
    email=request.email,
    registration_status="PAYMENT_COMPLETED"
)
```

#### Step 2: Auth0 Invitation
- Admin manually sends Auth0 invitation
- Status updated to "AUTH0_INVITE_SENT"

#### Step 3: User Registration
- User receives invitation and creates Auth0 account
- **Note**: Subscription record is NOT created until Auth0 registration completes
- This is because we need the `auth0_id` to create the subscription record

#### Step 4: Create Subscription Record
- Same as normal flow - happens in Auth0 callback handler

## Client App Integration

### Subscription Validation Middleware

The client app (`d-me`) uses middleware to validate subscriptions:

1. **Lookup by Auth0 ID**:
   ```python
   # Client app middleware
   subscription = db.query(Subscription).filter(
       Subscription.user_id == auth0_id
   ).first()
   ```

2. **Check Expiry Date**:
   ```python
   if subscription.end_date > datetime.now():
       # Allow access
   else:
       # Check with Stripe for current status
   ```

3. **Live Stripe Validation**:
   ```python
   # If expired, check current status
   stripe_subscription = stripe.Subscription.retrieve(
       subscription.payment_method  # This is the Stripe subscription ID
   )
   ```

### Key Points for Client App

1. **user_id = auth0_id**: The `user_id` field in subscriptions table contains the Auth0 user ID
2. **payment_method = Stripe subscription ID**: Used for live Stripe queries
3. **end_date = Expiry date**: From Stripe's `current_period_end`

## Error Handling & Edge Cases

### Missing Auth0 ID in Admin Recovery
- **Problem**: Admin recovery only has email, not `auth0_id`
- **Solution**: Create `SubscriptionUser` record, send Auth0 invitation, create `Subscription` record only after Auth0 registration completes

### Failed Subscription Record Creation
- **Behavior**: Auth flow continues even if subscription record creation fails
- **Logging**: Errors are logged but don't block user registration
- **Recovery**: Admin can manually trigger subscription record creation

### Stripe API Failures
- **Client app**: Uses "fail open" approach - allows access if Stripe API fails
- **DME Admin**: Logs errors but continues auth flow

## Data Consistency

### Key Relationships
1. `SubscriptionUser.subscription_id` → Stripe subscription ID
2. `SubscriptionUser.auth0_id` → `Subscription.user_id`
3. `Subscription.payment_method` → Stripe subscription ID (same as #1)

### Validation Points
1. Both records should exist for complete registration
2. `auth0_id` should match between tables
3. Stripe subscription ID should be consistent

## Testing & Debugging

### Verify Complete Flow
1. Check `subscription_users` table for registration status
2. Check `subscriptions` table for client app access
3. Verify Stripe subscription is active
4. Test client app access with Auth0 login

### Common Issues
1. **Missing subscription record**: Check if Auth0 callback completed
2. **Client app denying access**: Verify `end_date` and Stripe status
3. **Auth loop**: Check Auth0 configuration and callback URL

## Environment Configuration

### DME Admin
```bash
STRIPE_API_KEY=sk_xxx
AUTH0_DOMAIN=xxx
AUTH0_CLIENT_ID=xxx
AUTH0_CLIENT_SECRET=xxx
```

### Client App
```bash
SUBSCRIPTION_VALIDATION_ENABLED=true
STRIPE_API_KEY=sk_xxx  # Same as DME Admin
```

## Security Considerations

1. **Stripe API Key**: Must be the same in both applications
2. **Auth0 Integration**: DME Admin handles user creation and linking
3. **Database Access**: Both apps need read/write access to shared tables
4. **Payment Method Field**: Contains subscription ID, not sensitive payment data