import json
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False, default='')
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    role          = db.Column(db.String(20), nullable=False, default='user')
    is_active     = db.Column(db.Integer, nullable=False, default=1)   # 0/1 — toggled by admin
    last_login    = db.Column(db.DateTime, nullable=True)

    plan            = db.Column(db.String(20), nullable=False, default='free')  # 'free' | 'pro' | 'enterprise'
    plan_expires_at = db.Column(db.DateTime, nullable=True)   # None for free plan
    analyses_count_month        = db.Column(db.Integer, nullable=False, default=0)
    recommandations_count_month = db.Column(db.Integer, nullable=False, default=0)
    # Lazy month-rollover: counters reset on first request after a new month, not via cron
    counters_reset_at = db.Column(db.DateTime, default=datetime.utcnow)

    zone_analyses    = db.relationship('ZoneAnalysisHistory', backref='user', lazy=True)
    forecasts        = db.relationship('ForecastHistory', backref='user', lazy=True)
    roi_calculations = db.relationship('ROIHistory', backref='user', lazy=True)

    def effective_plan(self) -> str:
        """Returns 'free' if the paid plan has expired, otherwise the stored plan."""
        if self.plan in (None, '', 'free'):
            return 'free'
        if self.plan_expires_at and self.plan_expires_at < datetime.utcnow():
            return 'free'
        return self.plan

    def to_public_dict(self) -> dict:
        return {
            'id':                          self.id,
            'name':                        self.name,
            'email':                       self.email,
            'role':                        getattr(self, 'role', 'user'),
            'is_active':                   int(getattr(self, 'is_active', 1) or 0),
            'last_login':                  self.last_login.isoformat() if getattr(self, 'last_login', None) else None,
            'plan':                        self.effective_plan(),
            'plan_expires_at':             self.plan_expires_at.isoformat() if self.plan_expires_at else None,
            'analyses_count_month':        int(self.analyses_count_month or 0),
            'recommandations_count_month': int(self.recommandations_count_month or 0),
            'created_at':                  self.created_at.isoformat() if self.created_at else None,
        }


class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, nullable=True)   # nullable: system actions have no user
    action     = db.Column(db.String(50), nullable=False)
    details    = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':         self.id,
            'user_id':    self.user_id,
            'action':     self.action,
            'details':    self.details,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ErrorLog(db.Model):
    __tablename__ = 'error_logs'
    id         = db.Column(db.Integer, primary_key=True)
    message    = db.Column(db.Text, nullable=False)
    page       = db.Column(db.String(200), nullable=True)
    user_id    = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':         self.id,
            'message':    self.message,
            'page':       self.page,
            'user_id':    self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ZoneAnalysisHistory(db.Model):
    __tablename__ = 'zone_analysis_history'
    id                 = db.Column(db.Integer, primary_key=True)
    user_id            = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    wilaya_code        = db.Column(db.Integer, nullable=False)
    wilaya_name        = db.Column(db.String(100))
    target_capacity_mw = db.Column(db.Float, nullable=False)
    objective          = db.Column(db.String(50), default='utility')
    result_json        = db.Column(db.Text)
    processing_time_ms = db.Column(db.Float)
    created_at         = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':                 self.id,
            'type':               'zone_analysis',
            'wilaya_code':        self.wilaya_code,
            'wilaya_name':        self.wilaya_name,
            'target_capacity_mw': self.target_capacity_mw,
            'objective':          self.objective,
            'result':             json.loads(self.result_json) if self.result_json else None,
            'processing_time_ms': self.processing_time_ms,
            'created_at':         self.created_at.isoformat(),
        }


class ForecastHistory(db.Model):
    __tablename__ = 'forecast_history'
    id                 = db.Column(db.Integer, primary_key=True)
    user_id            = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    wilaya_code        = db.Column(db.Integer, nullable=False)
    wilaya_name        = db.Column(db.String(100))
    model_id           = db.Column(db.String(50), nullable=False)
    variable           = db.Column(db.String(20), nullable=False)
    horizon            = db.Column(db.String(10), nullable=False)
    metrics_json       = db.Column(db.Text)
    result_json        = db.Column(db.Text)
    processing_time_ms = db.Column(db.Float)
    created_at         = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':                 self.id,
            'type':               'forecast',
            'wilaya_code':        self.wilaya_code,
            'wilaya_name':        self.wilaya_name,
            'model_id':           self.model_id,
            'variable':           self.variable,
            'horizon':            self.horizon,
            'metrics':            json.loads(self.metrics_json) if self.metrics_json else None,
            'result':             json.loads(self.result_json) if self.result_json else None,
            'processing_time_ms': self.processing_time_ms,
            'created_at':         self.created_at.isoformat(),
        }


class ROIHistory(db.Model):
    __tablename__ = 'roi_history'
    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    wilaya_code   = db.Column(db.String(20))
    wilaya_name   = db.Column(db.String(100))
    capacity_mw   = db.Column(db.Float, nullable=False)
    scenario      = db.Column(db.String(20), default='moyen')
    capex         = db.Column(db.Float)
    npv           = db.Column(db.Float)
    irr           = db.Column(db.Float)
    payback_years = db.Column(db.Float)
    lcoe_usd_kwh  = db.Column(db.Float)
    result_json   = db.Column(db.Text)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':           self.id,
            'type':         'roi',
            'wilaya_code':  self.wilaya_code,
            'wilaya_name':  self.wilaya_name,
            'capacity_mw':  self.capacity_mw,
            'scenario':     self.scenario,
            'capex':        self.capex,
            'npv':          self.npv,
            'irr':          self.irr,
            'payback_years': self.payback_years,
            'lcoe_usd_kwh': self.lcoe_usd_kwh,
            'result':       json.loads(self.result_json) if self.result_json else None,
            'created_at':   self.created_at.isoformat(),
        }


class Analysis(db.Model):
    __tablename__ = 'analyses'
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name        = db.Column(db.String(100), nullable=False)
    capacity_mw = db.Column(db.Float, nullable=False)
    wilaya_code = db.Column(db.String(10), nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)


class Report(db.Model):
    __tablename__ = 'reports'
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # nullable: system-generated reports
    title        = db.Column(db.String(200))
    report_type  = db.Column(db.String(50))
    wilaya_name  = db.Column(db.String(100))
    capacity_mw  = db.Column(db.Float)
    data_json    = db.Column(db.Text)
    pdf_path     = db.Column(db.String(255))
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':           self.id,
            'type':         'report',
            'title':        self.title,
            'report_type':  self.report_type,
            'wilaya_name':  self.wilaya_name,
            'capacity_mw':  self.capacity_mw,
            'pdf_path':     self.pdf_path,
            'generated_at': self.generated_at.isoformat(),
        }