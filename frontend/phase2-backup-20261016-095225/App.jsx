
import { useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  ClipboardList,
  Search,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Download,
  LayoutDashboard,
  LogOut,
  RefreshCw,
  ShieldCheck,
  Users,
  Wallet,
  BriefcaseBusiness,
  XCircle,
  Menu,
  X,
} from "lucide-react";

import api from "./api";
import "./App.css";

function localDate(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function daysFromNow(days) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return localDate(date);
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(`${String(value).slice(0, 10)}T00:00:00`);
  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatTime(value) {
  if (!value) return "—";
  return new Date(value).toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function currency(value) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function messageFromError(error) {
  const detail = error.response?.data?.detail;

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || "Invalid input").join(", ");
  }

  return error.message || "Something went wrong. Please try again.";
}

function StatusBadge({ value }) {
  const normalized = String(value || "")
    .toLowerCase()
    .replace(/\s+/g, "-");

  return (
    <span className={`status-badge status-${normalized}`}>
      <span className="status-dot" />
      {value || "Unknown"}
    </span>
  );
}

function StatCard({ label, value, detail, icon: Icon, tone = "blue" }) {
  return (
    <article className="stat-card">
      <div className="stat-card-top">
        <span className={`stat-icon stat-icon-${tone}`}>
          <Icon size={21} strokeWidth={2} />
        </span>
        <span className="stat-card-detail">{detail}</span>
      </div>
      <p className="stat-label">{label}</p>
      <div className="stat-value">{value}</div>
    </article>
  );
}

function EmptyState({ title, description }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">
        <BriefcaseBusiness size={24} />
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}

const initialEmployeeForm = () => ({
  full_name: "",
  email: "",
  password: "",
  employee_code: "",
  department: "IT",
  designation: "",
  joining_date: localDate(),
  salary: "25000",
  phone: "",
  address: "",
});

const initialLeaveForm = () => ({
  leave_type: "Casual",
  start_date: daysFromNow(7),
  end_date: daysFromNow(7),
  reason: "",
});

const initialAuditFilters = () => ({
  actor_user_id: "",
  actor_name: "",
  action: "",
  entity_type: "",
  entity_id: "",
  start_date: "",
  end_date: "",
});

const AUDIT_PAGE_SIZE = 10;

const emptyDashboard = {
  employee: null,
  employees: [],
  attendance: [],
  attendanceSummary: null,
  leaves: [],
  pendingLeaves: [],
  balances: [],
  payroll: [],
};

function App() {
  const [user, setUser] = useState(null);
  const [booting, setBooting] = useState(true);
  const [loggingIn, setLoggingIn] = useState(false);

  const [loginForm, setLoginForm] = useState({
    email: "",
    password: "",
  });

  const [loginError, setLoginError] = useState("");

  const [activePage, setActivePage] = useState("Dashboard");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [dashboard, setDashboard] = useState(emptyDashboard);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const [leaveForm, setLeaveForm] = useState(initialLeaveForm);
  const [employeeForm, setEmployeeForm] = useState(initialEmployeeForm);

  // State used by the Employee Edit form.
  const [editingEmployee, setEditingEmployee] = useState(null);

  const [employeeEditForm, setEmployeeEditForm] = useState({
    employee_code: "",
    department: "",
    designation: "",
    joining_date: "",
    salary: "",
    phone: "",
    address: "",
  });

  // Read-only audit history and server-side filters/pagination.
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditLoaded, setAuditLoaded] = useState(false);
  const [auditSkip, setAuditSkip] = useState(0);
  const [auditHasNext, setAuditHasNext] = useState(false);
  const [auditFilters, setAuditFilters] = useState(initialAuditFilters);

  const isManagement = ["Admin", "HR"].includes(user?.role);
  const currentMonth = new Date().getMonth() + 1;
  const currentYear = new Date().getFullYear();

  const navigation = isManagement
    ? [
        { label: "Dashboard", icon: LayoutDashboard },
        { label: "Employees", icon: Users },
        { label: "Leave Management", icon: CalendarDays },
        { label: "Payroll", icon: Wallet },
        { label: "Audit Logs", icon: ClipboardList },
      ]
    : [
        { label: "Dashboard", icon: LayoutDashboard },
        { label: "Attendance", icon: Clock3 },
        { label: "My Leave", icon: CalendarDays },
        { label: "My Payroll", icon: Wallet },
      ];

  useEffect(() => {
    let cancelled = false;
    const token = localStorage.getItem("hrms_token");

    if (!token) {
      setBooting(false);

      return () => {
        cancelled = true;
      };
    }

    api
      .get("/auth/me")
      .then((response) => {
        if (!cancelled) setUser(response.data);
      })
      .catch(() => {
        localStorage.removeItem("hrms_token");
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setBooting(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (user) {
      loadDashboard();
    }

    // Reload when the authenticated account changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, user?.role]);

  async function loadDashboard() {
    if (!user) return;

    setLoading(true);
    setError("");

    try {
      if (["Admin", "HR"].includes(user.role)) {
        const results = await Promise.allSettled([
          api.get("/employees/", {
            params: { include_inactive: true },
          }),

          api.get("/leaves/", {
            params: { leave_status: "Pending" },
          }),

          api.get("/payroll/", {
            params: {
              month: currentMonth,
              year: currentYear,
            },
          }),
        ]);

        setDashboard((previous) => ({
          ...previous,

          employees:
            results[0].status === "fulfilled"
              ? results[0].value.data
              : previous.employees,

          pendingLeaves:
            results[1].status === "fulfilled"
              ? results[1].value.data
              : previous.pendingLeaves,

          payroll:
            results[2].status === "fulfilled"
              ? results[2].value.data
              : previous.payroll,
        }));

        if (results.every((result) => result.status === "rejected")) {
          setError(
            "Unable to load management data. Check the backend and your account permissions.",
          );
        }
      } else {
        const results = await Promise.allSettled([
          api.get("/employees/me"),

          api.get("/attendance/me"),

          api.get("/attendance/summary", {
            params: {
              month: currentMonth,
              year: currentYear,
            },
          }),

          api.get("/leaves/me"),
          api.get("/leaves/balances/me"),
          api.get("/payroll/me"),
        ]);

        setDashboard((previous) => ({
          ...previous,

          employee:
            results[0].status === "fulfilled"
              ? results[0].value.data
              : previous.employee,

          attendance:
            results[1].status === "fulfilled"
              ? results[1].value.data
              : previous.attendance,

          attendanceSummary:
            results[2].status === "fulfilled"
              ? results[2].value.data
              : previous.attendanceSummary,

          leaves:
            results[3].status === "fulfilled"
              ? results[3].value.data
              : previous.leaves,

          balances:
            results[4].status === "fulfilled"
              ? results[4].value.data
              : previous.balances,

          payroll:
            results[5].status === "fulfilled"
              ? results[5].value.data
              : previous.payroll,
        }));

        if (results.every((result) => result.status === "rejected")) {
          setError(
            "Unable to load your dashboard. Check your employee profile and backend connection.",
          );
        }
      }
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleLogin(event) {
    event.preventDefault();
    setLoggingIn(true);
    setLoginError("");

    try {
      const response = await api.post("/auth/login", loginForm);

      localStorage.setItem("hrms_token", response.data.access_token);

      const profile = await api.get("/auth/me");

      setDashboard(emptyDashboard);
      setUser(profile.data);
      setActivePage("Dashboard");
      setNotice(`Welcome, ${profile.data.full_name}.`);
    } catch (err) {
      localStorage.removeItem("hrms_token");
      setLoginError(messageFromError(err));
    } finally {
      setLoggingIn(false);
    }
  }

  function handleLogout() {
    localStorage.removeItem("hrms_token");

    setUser(null);
    setDashboard(emptyDashboard);
    setActivePage("Dashboard");
    setMobileMenuOpen(false);
    setNotice("");
    setError("");
    setLoginError("");
    setLoginForm({ email: "", password: "" });
  }

  function navigate(page) {
    setActivePage(page);
    setMobileMenuOpen(false);
    setNotice("");
    setError("");

    if (page === "Audit Logs" && isManagement) {
      void loadAuditLogs(0, auditFilters);
    }
  }

  async function loadAuditLogs(skipValue = auditSkip, filters = auditFilters) {
    if (!isManagement) return;

    setAuditLoading(true);
    setError("");

    try {
      const params = {
        skip: skipValue,
        limit: AUDIT_PAGE_SIZE,
      };

      if (String(filters.actor_user_id || "").trim()) {
        params.actor_user_id = Number(filters.actor_user_id);
      }
      if (String(filters.actor_name || "").trim()) {
        params.actor_name = filters.actor_name.trim();
      }
      if (String(filters.action || "").trim()) {
        params.action = filters.action.trim();
      }
      if (String(filters.entity_type || "").trim()) {
        params.entity_type = filters.entity_type.trim();
      }
      if (String(filters.entity_id || "").trim()) {
        params.entity_id = filters.entity_id.trim();
      }
      if (filters.start_date) params.start_date = filters.start_date;
      if (filters.end_date) params.end_date = filters.end_date;

      const response = await api.get("/audit-logs/", { params });

      if (!Array.isArray(response.data)) {
        throw new Error("The audit logs API returned an unexpected response.");
      }

      setAuditLogs(response.data);
      setAuditSkip(skipValue);
      setAuditHasNext(response.data.length === AUDIT_PAGE_SIZE);
      setAuditLoaded(true);
    } catch (err) {
      setAuditLogs([]);
      setAuditHasNext(false);
      setAuditLoaded(true);
      setError(messageFromError(err));
    } finally {
      setAuditLoading(false);
    }
  }

  async function handleAuditFilterSubmit(event) {
    event.preventDefault();
    await loadAuditLogs(0, auditFilters);
  }

  function resetAuditFilters() {
    const clearedFilters = initialAuditFilters();
    setAuditFilters(clearedFilters);
    void loadAuditLogs(0, clearedFilters);
  }

  function handleAuditFilterChange(field, value) {
    setAuditFilters((previous) => ({
      ...previous,
      [field]: value,
    }));
  }

  async function runAction(action, successMessage) {
    setNotice("");
    setError("");

    try {
      await action();
      setNotice(successMessage);
      await loadDashboard();
    } catch (err) {
      setError(messageFromError(err));
    }
  }

  async function handleAttendance(action) {
    await runAction(
      () => api.post(`/attendance/${action}`),

      action === "check-in"
        ? "Check-in recorded successfully."
        : "Check-out recorded successfully.",
    );
  }

  async function handleLeaveApplication(event) {
    event.preventDefault();
    setNotice("");
    setError("");

    try {
      await api.post("/leaves/", leaveForm);

      setNotice("Leave request submitted successfully.");
      setLeaveForm(initialLeaveForm());

      await loadDashboard();
    } catch (err) {
      setError(messageFromError(err));
    }
  }

  async function handleLeaveReview(leaveId, action) {
    await runAction(
      () => api.patch(`/leaves/${leaveId}/review`, { action }),

      `Leave request ${
        action === "approve" ? "approved" : "rejected"
      } successfully.`,
    );
  }

  async function handleEmployeeCreate(event) {
    event.preventDefault();
    setNotice("");
    setError("");

    try {
      const userResponse = await api.post("/auth/register", {
        full_name: employeeForm.full_name,
        email: employeeForm.email,
        password: employeeForm.password,
      });

      await api.post("/employees/", {
        user_id: userResponse.data.id,
        employee_code: employeeForm.employee_code,
        department: employeeForm.department,
        designation: employeeForm.designation,
        joining_date: employeeForm.joining_date,
        salary: Number(employeeForm.salary),
        phone: employeeForm.phone || null,
        address: employeeForm.address || null,
      });

      setEmployeeForm(initialEmployeeForm());
      setNotice("Employee account and employment profile created.");

      await loadDashboard();
    } catch (err) {
      setError(
        `${messageFromError(err)} If account registration succeeded but employee creation failed, check MySQL before retrying.`,
      );
    }
  }

  // Open the edit form with the selected employee's existing values.
  function startEmployeeEdit(employee) {
    setEditingEmployee(employee);

    setEmployeeEditForm({
      employee_code: employee.employee_code || "",
      department: employee.department || "",
      designation: employee.designation || "",

      joining_date: employee.joining_date
        ? String(employee.joining_date).slice(0, 10)
        : "",

      salary: String(employee.salary ?? ""),
      phone: employee.phone || "",
      address: employee.address || "",
    });

    setNotice("");
    setError("");
  }

  // Save employee changes through PATCH /employees/{employee_id}.
  async function handleEmployeeUpdate(event) {
    event.preventDefault();

    if (!editingEmployee) return;

    setNotice("");
    setError("");

    const payload = {
      employee_code: employeeEditForm.employee_code.trim(),
      department: employeeEditForm.department.trim(),
      designation: employeeEditForm.designation.trim(),
      joining_date: employeeEditForm.joining_date,
      salary: Number(employeeEditForm.salary),
      phone: employeeEditForm.phone.trim() || null,
      address: employeeEditForm.address.trim() || null,
    };

    try {
      await api.patch(
        `/employees/${editingEmployee.id}`,
        payload,
      );

      setNotice("Employee details updated successfully.");
      setEditingEmployee(null);

      await loadDashboard();
    } catch (err) {
      setError(messageFromError(err));
    }
  }

  // Deactivate an employee account without permanently deleting its record.
  async function handleEmployeeDeactivate(employee) {
    if (!employee.is_active) {
      setError("This employee is already inactive.");
      return;
    }

    const confirmed = window.confirm(
      `Deactivate employee ${employee.employee_code}? Their account will no longer be able to log in.`,
    );

    if (!confirmed) return;

    await runAction(
      () => api.patch(`/employees/${employee.id}/deactivate`),

      `Employee ${employee.employee_code} deactivated successfully.`,
    );
  }

  async function handlePayrollGenerate(event) {
    event.preventDefault();

    const form = new FormData(event.currentTarget);

    await runAction(
      () =>
        api.post("/payroll/generate", null, {
          params: {
            employee_id: Number(form.get("employee_id")),
            month: Number(form.get("month")),
            year: Number(form.get("year")),
          },
        }),

      "Payroll generated successfully.",
    );
  }

  async function handlePayrollAction(payrollId, action) {
    await runAction(
      () => api.post(`/payroll/${payrollId}/${action}`),

      action === "lock"
        ? "Payroll locked successfully."
        : "Salary credit simulation recorded successfully.",
    );
  }

  async function handleSalarySlipDownload(payrollId) {
    setNotice("");
    setError("");

    try {
      const response = await api.get(
        `/salary-slips/${payrollId}/download`,
        { responseType: "blob" },
      );

      const fileUrl = URL.createObjectURL(response.data);
      const link = document.createElement("a");

      link.href = fileUrl;
      link.download = `salary_slip_${payrollId}.pdf`;

      document.body.appendChild(link);
      link.click();
      link.remove();

      URL.revokeObjectURL(fileUrl);

      setNotice("Salary slip download started.");
    } catch (err) {
      setError(messageFromError(err));
    }
  }

  const pageTitle =
    navigation.find((item) => item.label === activePage)?.label ||
    activePage;

  const totalRemainingLeave = dashboard.balances.reduce(
    (sum, item) =>
      sum +
      Math.max(
        0,
        Number(item.total_days || 0) - Number(item.used_days || 0),
      ),
    0,
  );

  if (booting) {
    return (
      <div className="loading-screen">
        <div className="loading-brand">
          <ShieldCheck size={27} />
        </div>

        <p>Loading PeopleDesk HRMS</p>
        <span className="loading-spinner" />
      </div>
    );
  }

  if (!user) {
    return (
      <main className="auth-page">
        <div className="auth-orb auth-orb-one" />
        <div className="auth-orb auth-orb-two" />

        <section className="auth-card">
          <div className="auth-showcase">
            <div className="auth-brand">
              <div className="auth-brand-icon">
                <ShieldCheck size={27} />
              </div>

              <div>
                <div className="auth-brand-name">PeopleDesk</div>
                <div className="auth-brand-caption">HUMAN RESOURCES</div>
              </div>
            </div>

            <div className="auth-showcase-content">
              <div className="auth-pill">
                <span className="auth-live-dot" />
                ONE WORKSPACE. EVERY POSSIBILITY.
              </div>

              <h1>
                Great teams
                <br />
                start with <span>great people.</span>
              </h1>

              <p className="auth-description">
                The smarter workspace for managing your people, attendance,
                leave and payroll — all in one place.
              </p>

              <div className="auth-feature-list">
                <div className="auth-feature">
                  <span className="auth-feature-check">✓</span>
                  Secure role-based access
                </div>

                <div className="auth-feature">
                  <span className="auth-feature-check">✓</span>
                  Simple employee self-service
                </div>

                <div className="auth-feature">
                  <span className="auth-feature-check">✓</span>
                  Clear attendance and payroll records
                </div>
              </div>

              <div className="auth-mini-panel">
                <div className="auth-mini-icon">
                  <Activity size={21} />
                </div>

                <div>
                  <div className="auth-mini-title">
                    Your people, connected.
                  </div>

                  <div className="auth-mini-subtitle">
                    One secure place for everyday HR.
                  </div>
                </div>

                <ShieldCheck className="auth-mini-shield" size={23} />
              </div>
            </div>

            <div className="auth-showcase-footer">
              <span>© {new Date().getFullYear()} PeopleDesk HRMS</span>
              <span>Built for better workplaces</span>
            </div>
          </div>

          <div className="auth-form-panel">
            <div className="auth-form-content">
              <div className="auth-mobile-brand">
                <div className="auth-brand-icon">
                  <ShieldCheck size={25} />
                </div>

                <span>PeopleDesk HRMS</span>
              </div>

              <div className="auth-form-icon">
                <ShieldCheck size={27} />
              </div>

              <div className="auth-welcome-label">WELCOME BACK</div>

              <h2>Sign in to your workspace</h2>

              <p className="auth-form-description">
                Enter your company account details to continue.
              </p>

              <form onSubmit={handleLogin} className="auth-form">
                <label className="auth-label" htmlFor="hrms-email">
                  Email address
                </label>

                <div className="auth-input-wrap">
                  <input
                    id="hrms-email"
                    type="email"
                    autoComplete="username"
                    placeholder="name@company.com"
                    value={loginForm.email}
                    onChange={(event) =>
                      setLoginForm({
                        ...loginForm,
                        email: event.target.value,
                      })
                    }
                    required
                  />
                </div>

                <label className="auth-label" htmlFor="hrms-password">
                  Password
                </label>

                <div className="auth-input-wrap">
                  <input
                    id="hrms-password"
                    type="password"
                    autoComplete="current-password"
                    placeholder="Enter your password"
                    value={loginForm.password}
                    onChange={(event) =>
                      setLoginForm({
                        ...loginForm,
                        password: event.target.value,
                      })
                    }
                    required
                  />
                </div>

                {loginError && (
                  <div className="auth-error" role="alert">
                    <XCircle size={17} />
                    <span>{loginError}</span>
                  </div>
                )}

                <button
                  className="auth-submit"
                  type="submit"
                  disabled={loggingIn}
                >
                  {loggingIn ? "Signing in..." : "Sign in"}
                  {!loggingIn && <ArrowRight size={19} />}
                </button>
              </form>

              <div className="auth-security-note">
                <ShieldCheck size={17} />

                <span>
                  Protected by secure authentication.
                  <br />
                  Your access depends on your assigned role.
                </span>
              </div>
            </div>
          </div>
        </section>
      </main>
    );
  }

  return (
    <div className="app-shell">
      {mobileMenuOpen && (
        <button
          className="mobile-backdrop"
          aria-label="Close navigation"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      <aside className={`sidebar ${mobileMenuOpen ? "sidebar-open" : ""}`}>
        <div className="sidebar-brand">
          <div className="sidebar-brand-icon">
            <ShieldCheck size={24} />
          </div>

          <div>
            <div className="sidebar-brand-name">PeopleDesk</div>
            <div className="sidebar-brand-subtitle">HR MANAGEMENT</div>
          </div>

          <button
            className="mobile-sidebar-close"
            onClick={() => setMobileMenuOpen(false)}
            aria-label="Close menu"
          >
            <X size={19} />
          </button>
        </div>

        <div className="sidebar-section-label">WORKSPACE</div>

        <nav className="sidebar-nav">
          {navigation.map(({ label, icon: Icon }) => (
            <button
              key={label}
              className={`nav-item ${
                activePage === label ? "nav-item-active" : ""
              }`}
              onClick={() => navigate(label)}
            >
              <Icon size={19} strokeWidth={1.9} />
              <span>{label}</span>

              {activePage === label && (
                <span className="nav-active-mark" />
              )}
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-help-card">
            <div className="sidebar-help-icon">
              <ShieldCheck size={19} />
            </div>

            <div>
              <div className="sidebar-help-title">Secure workspace</div>
              <div className="sidebar-help-text">
                Access controlled by your role
              </div>
            </div>
          </div>

          <div className="sidebar-user">
            <div className="avatar">
              {(user.full_name || "U").trim().charAt(0).toUpperCase()}
            </div>

            <div className="sidebar-user-info">
              <div className="sidebar-user-name">{user.full_name}</div>
              <div className="sidebar-user-role">{user.role}</div>
            </div>

            <button
              className="logout-button"
              onClick={handleLogout}
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="mobile-menu-button"
              onClick={() => setMobileMenuOpen(true)}
              aria-label="Open navigation"
            >
              <Menu size={21} />
            </button>

            <div>
              <div className="breadcrumb">
                <span>Workspace</span>
                <span className="breadcrumb-separator">/</span>
                <strong>{pageTitle}</strong>
              </div>

              <h1 className="page-heading">{pageTitle}</h1>
            </div>
          </div>

          <div className="topbar-right">
            <div className="topbar-date">
              <CalendarDays size={16} />

              {new Date().toLocaleDateString("en-IN", {
                day: "2-digit",
                month: "short",
                year: "numeric",
              })}
            </div>

            <button
              className="refresh-button"
              onClick={() =>
                activePage === "Audit Logs"
                  ? loadAuditLogs(auditSkip, auditFilters)
                  : loadDashboard()
              }
              disabled={loading || auditLoading}
              title={activePage === "Audit Logs" ? "Refresh audit logs" : "Refresh dashboard"}
            >
              <RefreshCw
                size={17}
                className={loading || auditLoading ? "spin-animation" : ""}
              />

              <span>Refresh</span>
            </button>
          </div>
        </header>

        <div className="page-content">
          {notice && (
            <div className="alert alert-success" role="status">
              <CheckCircle2 size={19} />
              <span>{notice}</span>

              <button
                onClick={() => setNotice("")}
                aria-label="Dismiss notice"
              >
                <X size={17} />
              </button>
            </div>
          )}

          {error && (
            <div className="alert alert-error" role="alert">
              <XCircle size={19} />
              <span>{error}</span>

              <button
                onClick={() => setError("")}
                aria-label="Dismiss error"
              >
                <X size={17} />
              </button>
            </div>
          )}

          {activePage === "Dashboard" && (
            <>
              <section className="welcome-banner">
                <div className="welcome-banner-content">
                  <span className="welcome-eyebrow">
                    {isManagement
                      ? "MANAGEMENT OVERVIEW"
                      : "EMPLOYEE SELF-SERVICE"}
                  </span>

                  <h2>
                    Welcome back, {user.full_name?.split(" ")[0] || "there"}!
                  </h2>

                  <p>
                    {isManagement
                      ? "Here is what's happening across your organization today."
                      : "Your workday, leave and salary information in one place."}
                  </p>

                  <div className="welcome-role">
                    <ShieldCheck size={15} />
                    Signed in as {user.role}
                  </div>
                </div>

                <div className="welcome-art">
                  <div className="welcome-art-circle welcome-art-circle-one" />
                  <div className="welcome-art-circle welcome-art-circle-two" />

                  <div className="welcome-art-icon">
                    {isManagement ? (
                      <Users size={46} />
                    ) : (
                      <Activity size={46} />
                    )}
                  </div>
                </div>
              </section>

              {isManagement ? (
                <section className="stats-grid">
                  <StatCard
                    label="Employee records"
                    value={dashboard.employees.length}
                    detail="All loaded records"
                    icon={Users}
                    tone="blue"
                  />

                  <StatCard
                    label="Pending leave requests"
                    value={dashboard.pendingLeaves.length}
                    detail="Awaiting review"
                    icon={CalendarDays}
                    tone="purple"
                  />

                  <StatCard
                    label="Monthly payroll records"
                    value={dashboard.payroll.length}
                    detail={`${currentMonth}/${currentYear}`}
                    icon={Wallet}
                    tone="cyan"
                  />
                </section>
              ) : (
                <section className="stats-grid">
                  <StatCard
                    label="Attendance records"
                    value={dashboard.attendance.length}
                    detail="Your recorded days"
                    icon={Clock3}
                    tone="blue"
                  />

                  <StatCard
                    label="Remaining leave balance"
                    value={`${totalRemainingLeave} days`}
                    detail="Across configured leave types"
                    icon={CalendarDays}
                    tone="purple"
                  />

                  <StatCard
                    label="Payroll records"
                    value={dashboard.payroll.length}
                    detail="Your salary history"
                    icon={Wallet}
                    tone="cyan"
                  />
                </section>
              )}

              {!isManagement && dashboard.employee && (
                <section className="content-card">
                  <div className="section-heading">
                    <div>
                      <h2>My employment profile</h2>
                      <p>Your current employment information.</p>
                    </div>

                    <div className="section-heading-icon">
                      <BriefcaseBusiness size={19} />
                    </div>
                  </div>

                  <div className="profile-grid">
                    {[
                      ["Employee code", dashboard.employee.employee_code],
                      ["Department", dashboard.employee.department],
                      ["Designation", dashboard.employee.designation],
                      [
                        "Joining date",
                        formatDate(dashboard.employee.joining_date),
                      ],
                      ["Monthly salary", currency(dashboard.employee.salary)],
                    ].map(([label, value]) => (
                      <div className="profile-item" key={label}>
                        <div className="profile-item-label">{label}</div>
                        <div className="profile-item-value">
                          {value || "—"}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <section className="content-card quick-actions-card">
                <div className="section-heading">
                  <div>
                    <h2>Quick actions</h2>
                    <p>Get to the tasks you use most.</p>
                  </div>
                </div>

                <div className="quick-actions-grid">
                  {isManagement ? (
                    <>
                      <button
                        className="quick-action"
                        onClick={() => navigate("Employees")}
                      >
                        <span className="quick-action-icon quick-action-blue">
                          <Users size={20} />
                        </span>

                        <span className="quick-action-text">
                          <strong>Manage employees</strong>
                          <small>View or add employee records</small>
                        </span>

                        <ArrowRight size={18} />
                      </button>

                      <button
                        className="quick-action"
                        onClick={() => navigate("Leave Management")}
                      >
                        <span className="quick-action-icon quick-action-purple">
                          <CalendarDays size={20} />
                        </span>

                        <span className="quick-action-text">
                          <strong>Review leave requests</strong>
                          <small>Approve or reject applications</small>
                        </span>

                        <ArrowRight size={18} />
                      </button>

                      <button
                        className="quick-action"
                        onClick={() => navigate("Payroll")}
                      >
                        <span className="quick-action-icon quick-action-cyan">
                          <Wallet size={20} />
                        </span>

                        <span className="quick-action-text">
                          <strong>Manage payroll</strong>
                          <small>Generate and process salaries</small>
                        </span>

                        <ArrowRight size={18} />
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        className="quick-action"
                        onClick={() => handleAttendance("check-in")}
                      >
                        <span className="quick-action-icon quick-action-blue">
                          <Clock3 size={20} />
                        </span>

                        <span className="quick-action-text">
                          <strong>Check in</strong>
                          <small>Start today's attendance</small>
                        </span>

                        <ArrowRight size={18} />
                      </button>

                      <button
                        className="quick-action"
                        onClick={() => navigate("My Leave")}
                      >
                        <span className="quick-action-icon quick-action-purple">
                          <CalendarDays size={20} />
                        </span>

                        <span className="quick-action-text">
                          <strong>Apply for leave</strong>
                          <small>Submit a leave request</small>
                        </span>

                        <ArrowRight size={18} />
                      </button>

                      <button
                        className="quick-action"
                        onClick={() => navigate("My Payroll")}
                      >
                        <span className="quick-action-icon quick-action-cyan">
                          <Download size={20} />
                        </span>

                        <span className="quick-action-text">
                          <strong>Salary slips</strong>
                          <small>View and download payroll PDFs</small>
                        </span>

                        <ArrowRight size={18} />
                      </button>
                    </>
                  )}
                </div>
              </section>
            </>
          )}

          {activePage === "Employees" && isManagement && (
            <>
              <section className="content-card">
                <div className="section-heading">
                  <div>
                    <h2>Add an employee</h2>
                    <p>Create an Employee login and its employment profile.</p>
                  </div>

                  <div className="section-heading-icon">
                    <Users size={20} />
                  </div>
                </div>

                <form className="data-form" onSubmit={handleEmployeeCreate}>
                  {[
                    ["full_name", "Full name", "text"],
                    ["email", "Email address", "email"],
                    ["password", "Initial password", "password"],
                    ["employee_code", "Employee code", "text"],
                    ["department", "Department", "text"],
                    ["designation", "Designation", "text"],
                    ["joining_date", "Joining date", "date"],
                    ["salary", "Monthly salary (INR)", "number"],
                    ["phone", "Phone number", "tel"],
                    ["address", "Address", "text"],
                  ].map(([key, label, type]) => (
                    <label className="form-field" key={key}>
                      <span>
                        {label}
                        {!["phone", "address"].includes(key) && <b> *</b>}
                      </span>

                      <input
                        type={type}
                        required={!["phone", "address"].includes(key)}
                        min={type === "number" ? "0.01" : undefined}
                        minLength={key === "password" ? 8 : undefined}
                        value={employeeForm[key]}
                        onChange={(event) =>
                          setEmployeeForm({
                            ...employeeForm,
                            [key]: event.target.value,
                          })
                        }
                      />
                    </label>
                  ))}

                  <div className="form-actions">
                    <button className="primary-button" type="submit">
                      <Users size={17} />
                      Create employee
                    </button>
                  </div>
                </form>
              </section>

              {/* Edit Employee form */}
              {editingEmployee && (
                <section className="content-card">
                  <div className="section-heading">
                    <div>
                      <h2>Edit employee</h2>
                      <p>
                        Update employment record #{editingEmployee.id}. The
                        employee login and role will remain unchanged.
                      </p>
                    </div>

                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => setEditingEmployee(null)}
                    >
                      Cancel
                    </button>
                  </div>

                  <form
                    className="data-form"
                    onSubmit={handleEmployeeUpdate}
                  >
                    {[
                      ["employee_code", "Employee code", "text"],
                      ["department", "Department", "text"],
                      ["designation", "Designation", "text"],
                      ["joining_date", "Joining date", "date"],
                      ["salary", "Monthly salary (INR)", "number"],
                      ["phone", "Phone number", "tel"],
                      ["address", "Address", "text"],
                    ].map(([key, label, type]) => (
                      <label className="form-field" key={key}>
                        <span>{label}</span>

                        <input
                          type={type}
                          required={!["phone", "address"].includes(key)}
                          min={type === "number" ? "0.01" : undefined}
                          step={type === "number" ? "0.01" : undefined}
                          value={employeeEditForm[key]}
                          onChange={(event) =>
                            setEmployeeEditForm({
                              ...employeeEditForm,
                              [key]: event.target.value,
                            })
                          }
                        />
                      </label>
                    ))}

                    <div className="form-actions">
                      <button className="primary-button" type="submit">
                        <CheckCircle2 size={17} />
                        Save changes
                      </button>

                      <button
                        className="secondary-button"
                        type="button"
                        onClick={() => setEditingEmployee(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                </section>
              )}

              {/* Employee Directory */}
              <section className="content-card">
                <div className="section-heading">
                  <div>
                    <h2>Employee directory</h2>
                    <p>{dashboard.employees.length} records loaded</p>
                  </div>
                </div>

                {dashboard.employees.length === 0 ? (
                  <EmptyState
                    title="No employee records"
                    description="Created employee profiles will appear here."
                  />
                ) : (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Employee</th>
                          <th>User ID</th>
                          <th>Department</th>
                          <th>Designation</th>
                          <th>Monthly salary</th>
                          <th>Status</th>
                          <th>Actions</th>
                        </tr>
                      </thead>

                      <tbody>
                        {dashboard.employees.map((employee) => (
                          <tr key={employee.id}>
                            <td>
                              <div className="table-primary">
                                {employee.employee_code}
                              </div>

                              <div className="table-secondary">
                                Record #{employee.id}
                              </div>
                            </td>

                            <td>{employee.user_id}</td>
                            <td>{employee.department}</td>
                            <td>{employee.designation}</td>

                            <td className="table-money">
                              {currency(employee.salary)}
                            </td>

                            <td>
                              <StatusBadge
                                value={
                                  employee.is_active ? "Active" : "Inactive"
                                }
                              />
                            </td>

                            <td>
                              <div className="employee-actions">
                                <button
                                  type="button"
                                  className="small-action-button employee-action-edit"
                                  onClick={() => startEmployeeEdit(employee)}
                                >
                                  Edit
                                </button>

                                {employee.is_active ? (
                                  <button
                                    type="button"
                                    className="small-action-button employee-action-deactivate"
                                    onClick={() =>
                                      handleEmployeeDeactivate(employee)
                                    }
                                  >
                                    Deactivate
                                  </button>
                                ) : (
                                  <span className="status-badge status-inactive">
                                    Inactive
                                  </span>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}

          {activePage === "Attendance" && !isManagement && (
            <>
              <section className="stats-grid stats-grid-two">
                <StatCard
                  label="Days present this month"
                  value={
                    dashboard.attendanceSummary?.total_days_present ?? 0
                  }
                  detail={`${currentMonth}/${currentYear}`}
                  icon={CalendarDays}
                  tone="blue"
                />

                <StatCard
                  label="Total working hours"
                  value={
                    dashboard.attendanceSummary?.total_working_hours ?? 0
                  }
                  detail="Calculated from check-in/out"
                  icon={Activity}
                  tone="cyan"
                />
              </section>

              <section className="content-card">
                <div className="section-heading">
                  <div>
                    <h2>Daily attendance</h2>
                    <p>Record the start and end of your workday.</p>
                  </div>
                </div>

                <div className="attendance-actions">
                  <button
                    className="primary-button"
                    onClick={() => handleAttendance("check-in")}
                  >
                    <Clock3 size={18} />
                    Check in
                  </button>

                  <button
                    className="secondary-button"
                    onClick={() => handleAttendance("check-out")}
                  >
                    <Clock3 size={18} />
                    Check out
                  </button>
                </div>
              </section>

              <section className="content-card">
                <div className="section-heading">
                  <div>
                    <h2>Attendance history</h2>
                    <p>Your recorded check-in and check-out times.</p>
                  </div>
                </div>

                {dashboard.attendance.length === 0 ? (
                  <EmptyState
                    title="No attendance records"
                    description="Your recorded workdays will appear here."
                  />
                ) : (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Check-in</th>
                          <th>Check-out</th>
                          <th>Working hours</th>
                        </tr>
                      </thead>

                      <tbody>
                        {dashboard.attendance.map((record) => (
                          <tr key={record.id}>
                            <td>{formatDate(record.attendance_date)}</td>
                            <td>{formatTime(record.check_in)}</td>

                            <td>
                              {record.check_out
                                ? formatTime(record.check_out)
                                : "Not checked out"}
                            </td>

                            <td>{record.working_hours ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}

          {(activePage === "My Leave" ||
            activePage === "Leave Management") && (
            <>
              {!isManagement && (
                <>
                  <section className="content-card">
                    <div className="section-heading">
                      <div>
                        <h2>Apply for leave</h2>
                        <p>Submit a request for Admin/HR review.</p>
                      </div>

                      <div className="section-heading-icon">
                        <CalendarDays size={20} />
                      </div>
                    </div>

                    <form
                      className="data-form"
                      onSubmit={handleLeaveApplication}
                    >
                      <label className="form-field">
                        <span>
                          Leave type <b>*</b>
                        </span>

                        <select
                          value={leaveForm.leave_type}
                          onChange={(event) =>
                            setLeaveForm({
                              ...leaveForm,
                              leave_type: event.target.value,
                            })
                          }
                        >
                          {["Casual", "Sick", "Earned", "Unpaid"].map(
                            (type) => (
                              <option value={type} key={type}>
                                {type}
                              </option>
                            ),
                          )}
                        </select>
                      </label>

                      <label className="form-field">
                        <span>
                          Start date <b>*</b>
                        </span>

                        <input
                          type="date"
                          min={localDate()}
                          required
                          value={leaveForm.start_date}
                          onChange={(event) =>
                            setLeaveForm({
                              ...leaveForm,
                              start_date: event.target.value,
                              end_date:
                                leaveForm.end_date < event.target.value
                                  ? event.target.value
                                  : leaveForm.end_date,
                            })
                          }
                        />
                      </label>

                      <label className="form-field">
                        <span>
                          End date <b>*</b>
                        </span>

                        <input
                          type="date"
                          min={leaveForm.start_date}
                          required
                          value={leaveForm.end_date}
                          onChange={(event) =>
                            setLeaveForm({
                              ...leaveForm,
                              end_date: event.target.value,
                            })
                          }
                        />
                      </label>

                      <label className="form-field form-field-full">
                        <span>
                          Reason <b>*</b>
                        </span>

                        <textarea
                          rows={4}
                          required
                          minLength={3}
                          maxLength={1000}
                          value={leaveForm.reason}
                          onChange={(event) =>
                            setLeaveForm({
                              ...leaveForm,
                              reason: event.target.value,
                            })
                          }
                          placeholder="Briefly describe your leave request..."
                        />
                      </label>

                      <div className="form-actions">
                        <button className="primary-button" type="submit">
                          <CalendarDays size={17} />
                          Submit leave request
                        </button>
                      </div>
                    </form>
                  </section>

                  <section className="stats-grid leave-balance-grid">
                    {dashboard.balances.map((balance) => (
                      <article className="balance-card" key={balance.id}>
                        <span className="balance-card-icon">
                          <CalendarDays size={20} />
                        </span>

                        <p>{balance.leave_type} leave</p>

                        <strong>
                          {Math.max(
                            0,
                            Number(balance.total_days) -
                              Number(balance.used_days),
                          )}
                        </strong>

                        <span className="balance-unit">
                          days remaining
                        </span>

                        <div className="balance-progress">
                          <span
                            style={{
                              width: `${
                                Number(balance.total_days) > 0
                                  ? Math.min(
                                      100,
                                      (Number(balance.used_days) /
                                        Number(balance.total_days)) *
                                        100,
                                    )
                                  : 0
                              }%`,
                            }}
                          />
                        </div>

                        <small>
                          {balance.used_days} of {balance.total_days} used
                        </small>
                      </article>
                    ))}
                  </section>
                </>
              )}

              {isManagement ? (
                <section className="content-card">
                  <div className="section-heading">
                    <div>
                      <h2>Pending leave requests</h2>
                      <p>
                        {dashboard.pendingLeaves.length} requests awaiting review
                      </p>
                    </div>
                  </div>

                  {dashboard.pendingLeaves.length === 0 ? (
                    <EmptyState
                      title="You're all caught up"
                      description="There are no pending leave requests to review."
                    />
                  ) : (
                    <div className="leave-request-list">
                      {dashboard.pendingLeaves.map((leave) => (
                        <article className="leave-request" key={leave.id}>
                          <div className="leave-request-date-icon">
                            <CalendarDays size={21} />
                          </div>

                          <div className="leave-request-body">
                            <div className="leave-request-title">
                              {leave.leave_type} leave · Employee #
                              {leave.employee_id}
                            </div>

                            <div className="leave-request-dates">
                              {formatDate(leave.start_date)} —{" "}
                              {formatDate(leave.end_date)}
                            </div>

                            <p>{leave.reason}</p>
                            <StatusBadge value={leave.status} />
                          </div>

                          <div className="leave-request-actions">
                            <button
                              className="approve-button"
                              onClick={() =>
                                handleLeaveReview(leave.id, "approve")
                              }
                            >
                              <CheckCircle2 size={16} />
                              Approve
                            </button>

                            <button
                              className="reject-button"
                              onClick={() =>
                                handleLeaveReview(leave.id, "reject")
                              }
                            >
                              <XCircle size={16} />
                              Reject
                            </button>
                          </div>
                        </article>
                      ))}
                    </div>
                  )}
                </section>
              ) : (
                <section className="content-card">
                  <div className="section-heading">
                    <div>
                      <h2>My leave history</h2>
                      <p>Track the status of your applications.</p>
                    </div>
                  </div>

                  {dashboard.leaves.length === 0 ? (
                    <EmptyState
                      title="No leave applications yet"
                      description="Submitted leave requests will appear here."
                    />
                  ) : (
                    <div className="table-wrap">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Leave type</th>
                            <th>Start date</th>
                            <th>End date</th>
                            <th>Status</th>
                            <th>LOP days</th>
                          </tr>
                        </thead>

                        <tbody>
                          {dashboard.leaves.map((leave) => (
                            <tr key={leave.id}>
                              <td className="table-primary">
                                {leave.leave_type}
                              </td>
                              <td>{formatDate(leave.start_date)}</td>
                              <td>{formatDate(leave.end_date)}</td>
                              <td>
                                <StatusBadge value={leave.status} />
                              </td>
                              <td>{leave.lop_days}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              )}
            </>
          )}

          {(activePage === "Payroll" || activePage === "My Payroll") && (
            <>
              {isManagement && (
                <section className="content-card">
                  <div className="section-heading">
                    <div>
                      <h2>Generate monthly payroll</h2>
                      <p>
                        Generate a payroll record for an existing employee ID.
                      </p>
                    </div>

                    <div className="section-heading-icon">
                      <Wallet size={20} />
                    </div>
                  </div>

                  <form
                    className="data-form"
                    onSubmit={handlePayrollGenerate}
                  >
                    <label className="form-field">
                      <span>
                        Employee record ID <b>*</b>
                      </span>

                      <input
                        type="number"
                        name="employee_id"
                        min="1"
                        required
                        placeholder="e.g. 1"
                      />
                    </label>

                    <label className="form-field">
                      <span>
                        Month <b>*</b>
                      </span>

                      <select name="month" defaultValue={currentMonth}>
                        {Array.from(
                          { length: 12 },
                          (_, index) => index + 1,
                        ).map((value) => (
                          <option value={value} key={value}>
                            {new Date(2000, value - 1).toLocaleString(
                              "en-IN",
                              { month: "long" },
                            )}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="form-field">
                      <span>
                        Year <b>*</b>
                      </span>

                      <input
                        type="number"
                        name="year"
                        min="2000"
                        max="2100"
                        required
                        defaultValue={currentYear}
                      />
                    </label>

                    <div className="form-actions">
                      <button className="primary-button" type="submit">
                        <Wallet size={17} />
                        Generate payroll
                      </button>
                    </div>
                  </form>
                </section>
              )}

              <section className="content-card">
                <div className="section-heading">
                  <div>
                    <h2>
                      {isManagement ? "Payroll records" : "My payroll history"}
                    </h2>

                    <p>
                      {isManagement
                        ? "Monthly salary records and processing actions."
                        : "Your salary records and downloadable PDF slips."}
                    </p>
                  </div>
                </div>

                {dashboard.payroll.length === 0 ? (
                  <EmptyState
                    title="No payroll records"
                    description="Generated payroll records will appear here."
                  />
                ) : (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          {isManagement && <th>Employee</th>}
                          <th>Period</th>
                          <th>Gross salary</th>
                          <th>LOP deduction</th>
                          <th>Net salary</th>
                          <th>Status</th>
                          <th>Actions</th>
                        </tr>
                      </thead>

                      <tbody>
                        {dashboard.payroll.map((record) => (
                          <tr key={record.id}>
                            {isManagement && (
                              <td>
                                <div className="table-primary">
                                  Employee #{record.employee_id}
                                </div>

                                <div className="table-secondary">
                                  Payroll #{record.id}
                                </div>
                              </td>
                            )}

                            <td>
                              {new Date(
                                record.year,
                                record.month - 1,
                              ).toLocaleString("en-IN", {
                                month: "short",
                                year: "numeric",
                              })}
                            </td>

                            <td>{currency(record.gross_salary)}</td>

                            <td className="deduction-value">
                              {currency(record.lop_deduction)}
                            </td>

                            <td className="table-money">
                              {currency(record.net_salary)}
                            </td>

                            <td>
                              <StatusBadge value={record.status} />
                            </td>

                            <td>
                              <div className="table-action-buttons">
                                <button
                                  className="icon-button"
                                  onClick={() =>
                                    handleSalarySlipDownload(record.id)
                                  }
                                  title="Download salary slip PDF"
                                  aria-label="Download salary slip"
                                >
                                  <Download size={17} />
                                </button>

                                {isManagement && !record.is_locked && (
                                  <button
                                    className="small-action-button small-action-lock"
                                    onClick={() =>
                                      handlePayrollAction(record.id, "lock")
                                    }
                                  >
                                    Lock
                                  </button>
                                )}

                                {isManagement &&
                                  record.is_locked &&
                                  record.status !== "Paid" && (
                                    <button
                                      className="small-action-button small-action-pay"
                                      onClick={() =>
                                        handlePayrollAction(
                                          record.id,
                                          "credit",
                                        )
                                      }
                                    >
                                      Simulate credit
                                    </button>
                                  )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <div className="payroll-disclaimer">
                  <ShieldCheck size={16} />
                  Salary credit is simulated only; it does not confirm an actual
                  bank transfer.
                </div>
              </section>
            </>
          )}

          {activePage === "Audit Logs" && isManagement && (
            <div className="audit-page-stack">
              <section className="audit-hero">
                <div className="audit-hero-content">
                  <span className="audit-kicker">SECURITY &amp; COMPLIANCE</span>
                  <h2>Audit trail</h2>
                  <p>
                    Review administrative and system activity across employees,
                    leave requests, attendance, and payroll.
                  </p>
                  <span className="audit-readonly-chip">
                    <ShieldCheck size={15} />
                    Read-only audit access
                  </span>
                </div>
                <div className="audit-hero-art" aria-hidden="true">
                  <span className="audit-orbit audit-orbit-one" />
                  <span className="audit-orbit audit-orbit-two" />
                  <span className="audit-hero-icon">
                    <ClipboardList size={38} />
                  </span>
                </div>
              </section>

              <section className="audit-metrics-grid" aria-label="Audit summary">
                <article className="audit-metric-card">
                  <span className="audit-metric-icon audit-metric-purple">
                    <ClipboardList size={20} />
                  </span>
                  <div className="audit-metric-copy">
                    <span>Events on this page</span>
                    <strong>{auditLogs.length}</strong>
                    <small>Up to {AUDIT_PAGE_SIZE} records per page</small>
                  </div>
                </article>
                <article className="audit-metric-card">
                  <span className="audit-metric-icon audit-metric-cyan">
                    <ShieldCheck size={20} />
                  </span>
                  <div className="audit-metric-copy">
                    <span>Access level</span>
                    <strong>{user.role}</strong>
                    <small>Authorized management access</small>
                  </div>
                </article>
                <article className="audit-metric-card">
                  <span className="audit-metric-icon audit-metric-blue">
                    <Activity size={20} />
                  </span>
                  <div className="audit-metric-copy">
                    <span>Current page</span>
                    <strong>{Math.floor(auditSkip / AUDIT_PAGE_SIZE) + 1}</strong>
                    <small>Newest events appear first</small>
                  </div>
                </article>
              </section>

              <section className="content-card audit-filter-card">
                <div className="section-heading">
                  <div>
                    <h2>Filter audit events</h2>
                    <p>
                      Narrow the history by actor, action, record type, or date.
                    </p>
                  </div>
                  <div className="section-heading-icon">
                    <Search size={20} />
                  </div>
                </div>

                <form className="data-form audit-filter-grid" onSubmit={handleAuditFilterSubmit}>
                  <label className="form-field">
                    <span>Actor user ID</span>
                    <input
                      type="number"
                      min="1"
                      value={auditFilters.actor_user_id}
                      onChange={(event) => handleAuditFilterChange("actor_user_id", event.target.value)}
                      placeholder="Any user"
                    />
                  </label>

                  <label className="form-field">
                    <span>Actor name</span>
                    <input
                      type="text"
                      maxLength="150"
                      value={auditFilters.actor_name}
                      onChange={(event) => handleAuditFilterChange("actor_name", event.target.value)}
                      placeholder="e.g. magesh"
                    />
                  </label>

                  <label className="form-field">
                    <span>Action</span>
                    <input
                      type="text"
                      maxLength="100"
                      value={auditFilters.action}
                      onChange={(event) => handleAuditFilterChange("action", event.target.value)}
                      placeholder="e.g. payroll.credit_simulated"
                    />
                  </label>

                  <label className="form-field">
                    <span>Entity type</span>
                    <select
                      value={auditFilters.entity_type}
                      onChange={(event) => handleAuditFilterChange("entity_type", event.target.value)}
                    >
                      <option value="">All entities</option>
                      <option value="employee">Employee</option>
                      <option value="attendance">Attendance</option>
                      <option value="leave">Leave</option>
                      <option value="payroll">Payroll</option>
                      <option value="user">User</option>
                    </select>
                  </label>

                  <label className="form-field">
                    <span>Entity ID</span>
                    <input
                      type="text"
                      maxLength="50"
                      value={auditFilters.entity_id}
                      onChange={(event) => handleAuditFilterChange("entity_id", event.target.value)}
                      placeholder="e.g. 2"
                    />
                  </label>

                  <label className="form-field">
                    <span>Start date</span>
                    <input
                      type="date"
                      value={auditFilters.start_date}
                      onChange={(event) => handleAuditFilterChange("start_date", event.target.value)}
                    />
                  </label>

                  <label className="form-field">
                    <span>End date</span>
                    <input
                      type="date"
                      value={auditFilters.end_date}
                      min={auditFilters.start_date || undefined}
                      onChange={(event) => handleAuditFilterChange("end_date", event.target.value)}
                    />
                  </label>

                  <div className="form-actions audit-filter-actions">
                    <button className="primary-button" type="submit" disabled={auditLoading}>
                      <Search size={16} />
                      Apply filters
                    </button>
                    <button className="secondary-button" type="button" onClick={resetAuditFilters} disabled={auditLoading}>
                      <RotateCcw size={16} />
                      Reset
                    </button>
                  </div>
                </form>
              </section>

              <section className="content-card audit-results-card">
                <div className="section-heading audit-results-heading">
                  <div>
                    <h2>Audit history</h2>
                    <p>All entries are displayed newest first. This page cannot modify audit records.</p>
                  </div>
                  <span className="audit-readonly-label">
                    <ShieldCheck size={14} /> Read only
                  </span>
                </div>

                {auditLoading ? (
                  <div className="audit-loading-state">
                    <span className="loading-spinner" />
                    <span>Loading audit history...</span>
                  </div>
                ) : auditLogs.length === 0 ? (
                  <EmptyState
                    title={auditLoaded ? "No audit entries found" : "Loading audit history"}
                    description={auditLoaded
                      ? "Try changing or clearing the filters to see more events."
                      : "Audit entries will appear here after the request completes."}
                  />
                ) : (
                  <>
                    <div className="table-wrap audit-table-wrap">
                      <table className="data-table audit-table">
                        <thead>
                          <tr>
                            <th>Event</th>
                            <th>Actor</th>
                            <th>Action</th>
                            <th>Affected record</th>
                            <th>Date &amp; time</th>
                            <th>Details</th>
                          </tr>
                        </thead>
                        <tbody>
                          {auditLogs.map((entry) => (
                            <tr key={entry.id}>
                              <td>
                                <div className="table-primary">#{entry.id}</div>
                                <div className="table-secondary">Audit event</div>
                              </td>
                              <td>
                                <div className="table-primary">{entry.actor_name || "System"}</div>
                                <div className="table-secondary">
                                  {entry.actor_role || "System"}
                                  {entry.actor_user_id != null ? ` · User #${entry.actor_user_id}` : " · No user ID"}
                                </div>
                              </td>
                              <td>
                                <code className="audit-action-code">{entry.action}</code>
                              </td>
                              <td>
                                <span className={`audit-entity-pill audit-entity-${String(entry.entity_type || "other").toLowerCase()}`}>
                                  {entry.entity_type || "unknown"}
                                </span>
                                <div className="table-secondary audit-entity-id">
                                  {entry.entity_id ? `Record #${entry.entity_id}` : "No record ID"}
                                </div>
                              </td>
                              <td>
                                <div className="audit-time-date">{formatDate(entry.created_at)}</div>
                                <div className="table-secondary">{formatTime(entry.created_at)}</div>
                              </td>
                              <td>
                                {entry.details && Object.keys(entry.details).length > 0 ? (
                                  <details className="audit-details">
                                    <summary>View details</summary>
                                    <pre>{JSON.stringify(entry.details, null, 2)}</pre>
                                  </details>
                                ) : (
                                  <span className="audit-no-details">No details</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    <div className="audit-pagination">
                      <span className="audit-page-indicator">
                        Page {Math.floor(auditSkip / AUDIT_PAGE_SIZE) + 1}
                        <span> · </span>
                        {auditLogs.length} {auditLogs.length === 1 ? "event" : "events"} shown
                      </span>
                      <div className="audit-pagination-actions">
                        <button
                          className="secondary-button audit-page-button"
                          type="button"
                          onClick={() => loadAuditLogs(Math.max(0, auditSkip - AUDIT_PAGE_SIZE), auditFilters)}
                          disabled={auditSkip === 0 || auditLoading}
                        >
                          <ChevronLeft size={16} /> Previous
                        </button>
                        <button
                          className="secondary-button audit-page-button"
                          type="button"
                          onClick={() => loadAuditLogs(auditSkip + AUDIT_PAGE_SIZE, auditFilters)}
                          disabled={!auditHasNext || auditLoading}
                        >
                          Next <ChevronRight size={16} />
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </section>
            </div>
          )}

          <footer className="app-footer">
            <span>PeopleDesk HRMS</span>
            <span>People · Process · Progress</span>
          </footer>
        </div>
      </main>
    </div>
  );
}

export default App;
