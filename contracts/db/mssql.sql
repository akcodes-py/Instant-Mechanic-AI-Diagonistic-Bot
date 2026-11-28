/* Transactional state. The status column is an ACID state machine; the
   conditional UPDATE below is what guarantees no mechanic takes two jobs. */
CREATE TABLE mechanics (
    mechanic_id     UNIQUEIDENTIFIER PRIMARY KEY,
    full_name       NVARCHAR(120) NOT NULL,
    phone           VARCHAR(15) NOT NULL UNIQUE,
    garage_name     NVARCHAR(160) NULL,
    verified        BIT NOT NULL DEFAULT 0,
    home_h3_res8    CHAR(15) NULL,
    created_at      DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE mechanic_skills (
    mechanic_id     UNIQUEIDENTIFIER NOT NULL REFERENCES mechanics(mechanic_id),
    skill           VARCHAR(40) NOT NULL,
    PRIMARY KEY (mechanic_id, skill)
);

CREATE TABLE bookings (
    booking_id      UNIQUEIDENTIFIER PRIMARY KEY,
    session_id      UNIQUEIDENTIFIER NULL,
    customer_name   NVARCHAR(120) NOT NULL,
    customer_phone  VARCHAR(15) NOT NULL,
    required_skill  VARCHAR(40) NOT NULL,
    urgency         VARCHAR(10) NOT NULL,
    h3_res7_index   CHAR(15) NOT NULL,
    lat             FLOAT NOT NULL,
    lon             FLOAT NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'SEARCHING',
    assigned_mechanic UNIQUEIDENTIFIER NULL REFERENCES mechanics(mechanic_id),
    photo_object_key NVARCHAR(512) NULL,
    created_at      DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at      DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT ck_booking_status CHECK (status IN
        ('SEARCHING','OFFERED','ASSIGNED','EN_ROUTE','ARRIVED','IN_REPAIR','COMPLETED','ESCALATED'))
);
CREATE INDEX ix_bookings_status_h3 ON bookings(status, h3_res7_index);

/* One mechanic can own at most one active job. Enforced by the filtered index. */
CREATE UNIQUE INDEX uq_active_mechanic
    ON bookings(assigned_mechanic)
    WHERE status IN ('ASSIGNED','EN_ROUTE','ARRIVED','IN_REPAIR');

CREATE TABLE invoices (
    invoice_id      UNIQUEIDENTIFIER PRIMARY KEY,
    booking_id      UNIQUEIDENTIFIER NOT NULL REFERENCES bookings(booking_id),
    amount_paise    BIGINT NOT NULL,
    currency        CHAR(3) NOT NULL DEFAULT 'INR',
    created_at      DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);

/* Atomic claim: exactly one row wins when two accepts race.
   UPDATE bookings SET status='ASSIGNED', assigned_mechanic=@mech
   WHERE booking_id=@booking AND status IN ('SEARCHING','OFFERED');  -- @@ROWCOUNT = 1 means won */

/* Local stand-in (SQLite) uses the identical conditional UPDATE and
   a partial unique index on assigned_mechanic for active statuses. */
