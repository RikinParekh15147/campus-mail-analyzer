import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import {
  LayoutDashboard,
  CalendarDays,
  BookOpen,
  CalendarCheck,
  Files,
  MessagesSquare,
  GraduationCap,
  CheckCheck,
  UserRound,
  ChartNoAxesCombined,
  Settings,
  ArrowUpRight,
  Plus,
  Search,
  ChevronRight,
  ChevronLeft,
  RefreshCw,
  Upload,
  Mail,
  ShieldCheck,
  Clock,
  Link,
  FileText,
  X,
  Check,
  AlertTriangle,
  Download,
  BrainCircuit,
  Sun,
  Inbox,
  ArrowRight,
  Bell,
  LogOut,
} from "lucide-react";
import "./styles.css";

const bridge = window.campus;
const nav = [
  ["Today", LayoutDashboard],
  ["Calendar", CalendarDays],
  ["Assignments", BookOpen],
  ["Events", CalendarCheck],
  ["Resources", Files],
  ["Replies", MessagesSquare],
  ["Marks", GraduationCap],
  ["Review", CheckCheck],
  ["Profile", UserRound],
  ["Models", ChartNoAxesCombined],
  ["Settings", Settings],
];
const kinds = {
  Assignments: "assignment",
  Events: "event",
  Resources: "resource",
  Replies: "reply_request",
  Marks: "grade",
  Review: "review",
  Profile: "profile_fact",
};
const today = () =>
  new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
const addDays = (day, n) => {
  const d = new Date(day + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};
const niceDate = (d) =>
  d
    ? new Date(d.slice(0, 10) + "T12:00:00").toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
      })
    : "Date to confirm";
const titleCase = (s) =>
  (s || "").replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const request = (path, method = "GET", body) =>
  bridge
    ? bridge.request(path, method, body)
    : Promise.reject(
        Error(
          "Launch through Electron to connect your private Python backend.",
        ),
      );

function App() {
  const [profiles, setProfiles] = useState([]),
    [profile, setProfile] = useState(null),
    [page, setPage] = useState("Today"),
    [dashboard, setDashboard] = useState(null),
    [data, setData] = useState([]),
    [extra, setExtra] = useState({}),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [toast, setToast] = useState(""),
    [modal, setModal] = useState(null),
    [query, setQuery] = useState(""),
    [week, setWeek] = useState(today()),
    [newName, setNewName] = useState(""),
    [jobCount, setJobCount] = useState(0),
    [reviewLimit, setReviewLimit] = useState(6);
  const generation = useRef(0);
  const flash = (message) => {
    setToast(message);
    setTimeout(() => setToast(""), 4500);
  };
  const perform = async (fn, message) => {
    setError("");
    setBusy(true);
    try {
      const value = await fn();
      if (message) flash(message);
      return value;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setBusy(false);
    }
  };
  const select = async (p) => {
    generation.current++;
    await perform(() => bridge.selectProfile(p.id));
    setProfile(p);
    setData([]);
    setDashboard(null);
    setExtra({});
    setPage("Today");
  };
  const refresh = async () => {
    const version = generation.current;
    try {
      const board = await request("/dashboard");
      if (version !== generation.current) return;
      setDashboard(board);
      let rows = [],
        additional = {};
      if (kinds[page]) rows = await request("/records/" + kinds[page]);
      if (page === "Calendar") {
        rows = await request(`/calendar?start=${week}&end=${addDays(week, 6)}`);
        additional.conflicts = await request(
          `/conflicts?start=${week}&end=${addDays(week, 6)}`,
        );
      }
      if (page === "Today") {
        additional.review = (await request("/records/review"))
          .filter((r) => r.status === "open")
          .slice(0, 3);
        additional.connections = await request("/connections");
      }
      if (page === "Models") additional.models = await request("/models");
      if (page === "Settings") {
        additional.settings = await request("/settings");
        additional.connections = await request("/connections");
        additional.jobs = (await request("/records/job")).slice(-8).reverse();
      }
      if (version !== generation.current) return;
      setData(rows);
      setExtra(additional);
    } catch (e) {
      if (version === generation.current) setError(e.message);
    }
  };
  useEffect(() => {
    if (bridge)
      bridge
        .profiles()
        .then(setProfiles)
        .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (profile) {
      setQuery("");
      refresh();
    }
  }, [profile, page, week]);
  useEffect(() => {
    if (!profile) return;
    let last = "";
    const timer = setInterval(async () => {
      try {
        const update = await request("/updates");
        setJobCount(update.jobs_running);
        if (update.version !== last) {
          last = update.version;
          refresh();
        }
      } catch {}
    }, 5000);
    return () => clearInterval(timer);
  }, [profile, page, week]);
  const mutate = async (path, body, message) => {
    const value = await perform(() => request(path, "POST", body), message);
    if (value) refresh();
    return value;
  };
  const feedback = (item, field, value) =>
    mutate(
      "/feedback",
      { record_id: item.id, field, value, expected_revision: item.revision },
      "Your choice is saved.",
    );
  const source = async (id) => {
    const item = await perform(() => request("/records/" + id + "/detail"));
    if (item) setModal({ type: "detail", item });
  };
  const upload = async () => {
    const item = await perform(() => bridge.upload(), "Attachment analyzed.");
    if (item) {
      setModal({ type: "detail", item });
      refresh();
    }
    return item;
  };
  const visible = data.filter((r) =>
    JSON.stringify([
      r.title,
      r.course,
      r.question,
      r.assessment,
      r.field,
      r.value,
    ])
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const openLink = (url) => perform(() => bridge.openUrl(url));
  const importSchedule = (kind) => setModal({ type: "schedule", kind });
  const headerAction = () =>
    page === "Calendar" ? (
      <>
        <button className="button" onClick={() => importSchedule("timetable")}>
          Import timetable
        </button>
        <button
          className="button primary"
          onClick={() => setModal({ type: "block" })}
        >
          <Plus size={16} /> Plan a block
        </button>
      </>
    ) : page === "Resources" ? (
      <button className="button primary" onClick={upload}>
        <Upload size={16} /> Add a document
      </button>
    ) : page === "Marks" ? (
      <button
        className="button primary"
        onClick={() => setModal({ type: "marks" })}
      >
        <Plus size={16} /> Extract results
      </button>
    ) : (
      <button
        className="button primary"
        onClick={() => setModal({ type: "notice" })}
      >
        <Plus size={16} /> Analyze a notice
      </button>
    );
  if (!profile)
    return (
      <div className="welcome">
        <div className="welcome-art">
          <div className="wordmark">
            <span className="logo">
              <Mail size={23} />
            </span>
            campus<span className="brand-dot">.</span>
          </div>
          <span className="eyebrow">LESS INBOX. MORE HEADSPACE.</span>
          <h1>
            Your campus,
            <br />
            without the clutter.
          </h1>
          <p>
            A quieter place for deadlines, classes, important documents, and
            everything that needs your attention.
          </p>
          <div className="welcome-tags">
            <span>
              <ShieldCheck size={16} /> Local-first
            </span>
            <span>
              <BrainCircuit size={16} /> Learns your preferences
            </span>
          </div>
          <div className="orbit-card">
            <CalendarCheck />
            <div>
              <strong>Your next chapter, organized.</strong>
              <p>One academic day at a time.</p>
            </div>
            <Check size={18} />
          </div>
        </div>
        <div className="welcome-form">
          <span className="eyebrow">YOUR PERSONAL WORKSPACE</span>
          <h2>Make room for what matters.</h2>
          <p>Create a private profile or pick up where you left off.</p>
          {profiles.map((p) => (
            <button
              className="profile-option"
              key={p.id}
              onClick={() => select(p)}
            >
              <span className="avatar">{p.name[0]}</span>
              <strong>{p.name}</strong>
              <ArrowRight size={18} />
            </button>
          ))}
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              const p = await perform(() => bridge.createProfile(newName));
              if (p) {
                setProfiles([...profiles, p]);
                setProfile(p);
              }
            }}
          >
            <label>
              Profile name
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="What should we call you?"
                required
              />
            </label>
            <button className="button primary wide" disabled={busy || !bridge}>
              Create my workspace <ArrowRight size={16} />
            </button>
          </form>
          {!bridge && (
            <div className="notice-box">
              Open the Electron desktop app to connect to your private Python
              backend.
            </div>
          )}
          {error && <div className="error">{error}</div>}
          <small>
            Your Gmail stays disconnected until you choose to connect it.
          </small>
        </div>
      </div>
    );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="wordmark">
          <span className="logo">
            <Mail size={21} />
          </span>
          campus<span className="brand-dot">.</span>
        </div>
        <div className="workspace-label">PERSONAL WORKSPACE</div>
        <nav>
          {nav.map(([name, Icon], i) => (
            <React.Fragment key={name}>
              {i === 8 && <div className="nav-divider" />}
              <button
                className={page === name ? "nav-item active" : "nav-item"}
                onClick={() => setPage(name)}
              >
                <Icon size={19} />
                <span>{name}</span>
                {name === "Review" && dashboard?.counts.review > 0 && (
                  <b>{dashboard.counts.review}</b>
                )}
              </button>
            </React.Fragment>
          ))}
        </nav>
        <div className="local-card">
          <span className="status-dot" />
          <strong>Works close to home</strong>
          <p>
            Your mail is processed locally.
            <br />
            Your preferences stay yours.
          </p>
          <ShieldCheck size={21} />
        </div>
        <button
          className="profile-switch"
          onClick={() => {
            generation.current++;
            setProfile(null);
            setData([]);
            setDashboard(null);
          }}
        >
          <span className="avatar">{profile.name[0]}</span>
          <span>
            <strong>{profile.name}</strong>
            <small>Private profile</small>
          </span>
          <LogOut size={16} />
        </button>
      </aside>
      <main>
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={13} />
            <strong>{page}</strong>
          </div>
          <div className="topbar-right">
            <span className="local-pill">
              <span className="status-dot" />{" "}
              {jobCount
                ? `${jobCount} background job${jobCount > 1 ? "s" : ""}`
                : "Local processing"}
            </span>
            <button
              className="icon-button"
              onClick={() => {
                setModal({ type: "notifications" });
                request("/records/notification").then((rows) =>
                  setModal({ type: "notifications", rows }),
                );
              }}
              aria-label="Notifications"
            >
              <Bell size={19} />
              {dashboard?.notifications.length > 0 && <i />}
            </button>
          </div>
        </header>
        <div className="page-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {page === "Today"
                  ? new Date(today() + "T12:00:00").toLocaleDateString(
                      "en-IN",
                      {
                        weekday: "long",
                        day: "numeric",
                        month: "long",
                        year: "numeric",
                      },
                    )
                  : "YOUR ACADEMIC WORKSPACE"}
              </div>
              <h1>
                {page === "Today"
                  ? `A little clarity, ${profile.name.split(" ")[0]}.`
                  : page === "Replies"
                    ? "Conversations that need you"
                    : page === "Review"
                      ? "A few things only you know"
                      : page === "Models"
                        ? "The learning behind the scenes"
                        : page}
              </h1>
              <p>
                {
                  {
                    Today: "Your academic day, thoughtfully brought together.",
                    Calendar:
                      "Classes, commitments, and a little breathing room.",
                    Assignments:
                      "Know what is due, and keep the right resources close.",
                    Events: "Choose what deserves a place in your day.",
                    Resources:
                      "Useful documents and links, connected to the right context.",
                    Replies:
                      "Outstanding requests, with the conversation behind them.",
                    Marks: "Your results, organized by course and assessment.",
                    Review: "Small answers make your workspace more personal.",
                    Profile:
                      "What we know, what needs confirmation, and what you can change.",
                    Models:
                      "Real training runs, transparent evaluation, and honest limitations.",
                    Settings:
                      "Your connections, your schedule, your preferences.",
                  }[page]
                }
              </p>
            </div>
            <div className="heading-actions">
              <button
                className="icon-button bordered"
                onClick={refresh}
                aria-label="Refresh"
              >
                <RefreshCw size={17} className={busy ? "spin" : ""} />
              </button>
              {headerAction()}
            </div>
          </div>
          {error && (
            <div className="error">
              <AlertTriangle size={17} />
              {error}
              <button onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {page === "Today" && (
            <>
              <div className="stats-grid">
                {[
                  ["Assignments", "assignments", BookOpen, "peach"],
                  ["Events found", "events", CalendarDays, "lavender"],
                  ["Replies needed", "replies", MessagesSquare, "blue"],
                  ["Ready for review", "review", CheckCheck, "green"],
                ].map(([label, key, Icon, color]) => (
                  <button
                    className="stat-card"
                    key={key}
                    onClick={() =>
                      setPage(
                        key === "replies"
                          ? "Replies"
                          : key === "review"
                            ? "Review"
                            : key === "events"
                              ? "Events"
                              : "Assignments",
                      )
                    }
                  >
                    <div>
                      <span className={"stat-icon " + color}>
                        <Icon size={20} />
                      </span>
                      <ArrowUpRight size={16} />
                    </div>
                    <strong>{dashboard?.counts[key] ?? "—"}</strong>
                    <span>{label}</span>
                  </button>
                ))}
              </div>
              <div className="dashboard-columns">
                <section>
                  <div className="briefing-card">
                    <div className="section-title">
                      <span className="eyebrow">
                        <Sun size={16} /> YOUR DAILY BRIEF
                      </span>
                      <span className="tag light">Source linked</span>
                    </div>
                    <h2>
                      {dashboard?.summary.items.length
                        ? "A few things to keep in focus."
                        : "A little space to get organized."}
                    </h2>
                    <p>
                      {dashboard?.summary.items.length
                        ? `${dashboard.summary.items.length} commitment${dashboard.summary.items.length > 1 ? "s" : ""} and action${dashboard.summary.items.length > 1 ? "s" : ""} in the next week.`
                        : "Connect Gmail or import your collected notices to bring your academic week into focus."}
                    </p>
                    {dashboard?.summary.items.slice(0, 3).map((item) => (
                      <div className="briefing-line" key={item.id}>
                        <span className="mini-dot" />
                        <span>{item.summary}</span>
                      </div>
                    ))}
                    <div className="briefing-bottom">
                      <button
                        onClick={() =>
                          setModal({
                            type: "summary",
                            report: dashboard?.summary,
                          })
                        }
                      >
                        Open weekly briefing <ArrowRight size={15} />
                      </button>
                      <span>
                        <BrainCircuit size={15} /> Generated locally
                      </span>
                    </div>
                  </div>
                  <div className="section-heading">
                    <h2>
                      On your radar{" "}
                      <span className="subtle-count">
                        {dashboard?.recent.length || 0}
                      </span>
                    </h2>
                    <button
                      className="text-button"
                      onClick={() => setPage("Assignments")}
                    >
                      View all <ArrowRight size={14} />
                    </button>
                  </div>
                  <div className="panel">
                    {dashboard?.recent.length ? (
                      dashboard.recent
                        .slice()
                        .reverse()
                        .map((item) => (
                          <div className="radar-row" key={item.id}>
                            <span
                              className={
                                "row-icon " +
                                (item.kind === "assignment"
                                  ? "peach"
                                  : "lavender")
                              }
                            >
                              {item.kind === "assignment" ? (
                                <BookOpen size={18} />
                              ) : (
                                <CalendarDays size={18} />
                              )}
                            </span>
                            <div className="row-main">
                              <strong>{item.title}</strong>
                              <small>
                                {item.course || "Course to confirm"} ·{" "}
                                {niceDate(item.due_date || item.date)}
                              </small>
                            </div>
                            <Importance item={item} onChange={feedback} />
                            <button
                              className="icon-button"
                              onClick={() => setModal({ type: "detail", item })}
                            >
                              <ChevronRight size={17} />
                            </button>
                          </div>
                        ))
                    ) : (
                      <Empty
                        icon={Inbox}
                        title="Your radar is ready"
                        text="Import collected notices or connect Gmail to start filling it."
                      />
                    )}
                  </div>
                </section>
                <aside className="right-rail">
                  <div className="panel review-panel">
                    <div className="section-title">
                      <h3>A quick check-in</h3>
                      <span className="tag amber">
                        {dashboard?.counts.review || 0}
                      </span>
                    </div>
                    <p className="muted">A little input goes a long way.</p>
                    {extra.review?.length ? (
                      extra.review.slice(0, 2).map((q) => (
                        <div className="quick-question" key={q.id}>
                          <strong>{q.question}</strong>
                          <button
                            className="text-button"
                            onClick={() => {
                              setPage("Review");
                            }}
                          >
                            Review this <ArrowRight size={14} />
                          </button>
                        </div>
                      ))
                    ) : (
                      <p className="small-muted">
                        Nothing waiting for your input.
                      </p>
                    )}
                    <button
                      className="button wide"
                      onClick={() => setPage("Review")}
                    >
                      Open review queue <ChevronRight size={15} />
                    </button>
                  </div>
                  <div className="panel connection-panel">
                    <h3>Stay connected</h3>
                    {["gmail", "calendar"].map((s) => (
                      <div className="connection-row" key={s}>
                        <span className="connection-icon">
                          {s === "gmail" ? (
                            <Mail size={18} />
                          ) : (
                            <CalendarDays size={18} />
                          )}
                        </span>
                        <div>
                          <strong>
                            {s === "gmail" ? "Gmail" : "Google Calendar"}
                          </strong>
                          <small>
                            {extra.connections?.[s]?.connected
                              ? "Connected"
                              : "Not connected"}
                          </small>
                        </div>
                        <span
                          className={
                            "mini-dot " +
                            (extra.connections?.[s]?.connected
                              ? "online"
                              : "offline")
                          }
                        />
                      </div>
                    ))}
                    <button
                      className="text-button"
                      onClick={() => setPage("Settings")}
                    >
                      Manage connections <ArrowUpRight size={14} />
                    </button>
                  </div>
                  <div className="tip-card">
                    <span>MADE FOR YOUR CAMPUS LIFE</span>
                    <h3>
                      Less noise.
                      <br />
                      More of what matters.
                    </h3>
                    <p>
                      Every correction helps your workspace understand you a
                      little better.
                    </p>
                    <div className="decor-lines">
                      <i />
                      <i />
                      <i />
                    </div>
                  </div>
                </aside>
              </div>
            </>
          )}
          {kinds[page] && (
            <div className="collection-toolbar">
              <div className="search">
                <Search size={17} />
                <input
                  placeholder={`Search ${page.toLowerCase()}…`}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              <span>{visible.length} records</span>
              {page === "Profile" && (
                <button
                  className="button"
                  onClick={() => setModal({ type: "profile" })}
                >
                  <Plus size={15} /> Add a confirmed detail
                </button>
              )}
            </div>
          )}
          {["Assignments", "Events"].includes(page) && (
            <div className="item-grid">
              {visible.map((item) => (
                <article className="panel academic-card" key={item.id}>
                  <div className="section-title">
                    <span className="tag">
                      {item.course || "Course unconfirmed"}
                    </span>
                    <Importance item={item} onChange={feedback} />
                  </div>
                  <h3>{item.title}</h3>
                  <p className="clamp">{item.description}</p>
                  <div className="item-date">
                    <Clock size={15} />
                    {niceDate(item.due_date || item.date)}
                    {item.date_precision === "date" && (
                      <small>time unspecified</small>
                    )}
                  </div>
                  <div className="resource-line">
                    <Files size={15} />
                    {item.resource_ids?.length || 0} related resources{" "}
                    <span>·</span>{" "}
                    {titleCase(
                      item.participation || item.relevance || item.status,
                    )}
                  </div>
                  <div className="card-footer">
                    <button
                      className="text-button"
                      onClick={() => setModal({ type: "detail", item })}
                    >
                      Details & evidence <ArrowUpRight size={14} />
                    </button>
                    {page === "Assignments" ? (
                      <button
                        className="button compact"
                        onClick={() =>
                          feedback(
                            item,
                            "status",
                            item.status === "complete" ? "open" : "complete",
                          )
                        }
                      >
                        <Check size={14} />
                        {item.status === "complete" ? "Reopen" : "Complete"}
                      </button>
                    ) : (
                      <select
                        className="mini-select"
                        value={item.participation || "unknown"}
                        onChange={(e) =>
                          feedback(item, "participation", e.target.value)
                        }
                      >
                        <option value="unknown">Not decided</option>
                        <option value="interested">Interested</option>
                        <option value="confirmed">Attending</option>
                        <option value="declined">Declined</option>
                        <option value="mandatory">Mandatory</option>
                      </select>
                    )}
                  </div>
                </article>
              ))}
              {!visible.length && (
                <Empty
                  icon={page === "Assignments" ? BookOpen : CalendarDays}
                  title={`No ${page.toLowerCase()} here yet`}
                  text="Analyze a notice or import your collected mail."
                />
              )}
            </div>
          )}
          {page === "Calendar" && (
            <>
              <div className="calendar-toolbar">
                <div>
                  <button
                    className="icon-button bordered"
                    onClick={() => setWeek(addDays(week, -7))}
                  >
                    <ChevronLeft size={17} />
                  </button>
                  <strong>
                    {niceDate(week)} — {niceDate(addDays(week, 6))}
                  </strong>
                  <button
                    className="icon-button bordered"
                    onClick={() => setWeek(addDays(week, 7))}
                  >
                    <ChevronRight size={17} />
                  </button>
                  <button
                    className="text-button"
                    onClick={() => setWeek(today())}
                  >
                    Today
                  </button>
                  <span className="tag">
                    {dashboard?.timezone || "Asia/Kolkata"}
                  </span>
                </div>
                <button
                  className="button"
                  onClick={() => importSchedule("holidays")}
                >
                  Import holiday list
                </button>
              </div>
              <div className="week-grid">
                {Array.from({ length: 7 }, (_, i) => {
                  const day = addDays(week, i);
                  return (
                    <div
                      className={
                        "day-column " + (day === today() ? "is-today" : "")
                      }
                      key={day}
                    >
                      <header>
                        <span>
                          {new Date(day + "T12:00").toLocaleDateString(
                            "en-IN",
                            { weekday: "short" },
                          )}
                        </span>
                        <strong>{day.slice(-2)}</strong>
                      </header>
                      {data
                        .filter((e) => e.date === day)
                        .map((e) => (
                          <button
                            className={
                              "calendar-event " +
                              (e.kind === "class"
                                ? "class-event"
                                : e.due_marker
                                  ? "deadline-event"
                                  : "")
                            }
                            key={e.id}
                            onClick={() =>
                              setModal({ type: "detail", item: e })
                            }
                          >
                            <small>
                              {e.start
                                ? new Date(e.start).toLocaleTimeString(
                                    "en-IN",
                                    {
                                      hour: "2-digit",
                                      minute: "2-digit",
                                      timeZone:
                                        dashboard?.timezone || "Asia/Kolkata",
                                    },
                                  )
                                : e.due_marker
                                  ? "Due date"
                                  : "Time to confirm"}
                            </small>
                            <strong>{e.title}</strong>
                          </button>
                        ))}
                    </div>
                  );
                })}
              </div>
              <div className="section-heading">
                <h2>Conflicts & breathing room</h2>
                <span className="tag">Changes need your approval</span>
              </div>
              {extra.conflicts?.length ? (
                extra.conflicts.map((c, i) => (
                  <div className="panel conflict-card" key={i}>
                    <AlertTriangle size={20} />
                    <div>
                      <strong>
                        {c.severity === "workload"
                          ? "Several deadlines share a date"
                          : `${c.a.title} × ${c.b.title}`}
                      </strong>
                      <p>{c.suggestion}</p>
                    </div>
                    {[c.a, c.b]
                      .filter((e) => e?.flexible && e.kind === "calendar_item")
                      .map((e) => (
                        <button
                          className="button"
                          key={e.id}
                          onClick={async () => {
                            const p = await mutate(
                              "/conflicts/" + e.id + "/propose",
                              {},
                              null,
                            );
                            if (p) setModal({ type: "proposal", item: p });
                          }}
                        >
                          Suggest another slot
                        </button>
                      ))}
                  </div>
                ))
              ) : (
                <div className="panel quiet-state">
                  <ShieldCheck size={20} />
                  <div>
                    <strong>No known conflicts in this window.</strong>
                    <p>
                      Checks include your timetable, confirmed events, and
                      connected calendar records.
                    </p>
                  </div>
                </div>
              )}
            </>
          )}
          {page === "Resources" && (
            <div className="item-grid">
              {visible.map((item) => (
                <article className="panel resource-card" key={item.id}>
                  <span className="large-file-icon">
                    {item.url ? <Link size={25} /> : <FileText size={25} />}
                  </span>
                  <span className="tag">
                    {item.url
                      ? item.drive_link_only
                        ? "Drive link"
                        : "Web resource"
                      : item.status || "Document"}
                  </span>
                  <h3>{item.title || item.filename || "Attachment"}</h3>
                  <p>{item.course || "Linked from your notices"}</p>
                  {item.sanitized_placeholder && (
                    <small>URL anonymized in this dataset</small>
                  )}
                  <div className="card-footer">
                    <button
                      className="text-button"
                      onClick={() => setModal({ type: "detail", item })}
                    >
                      View context <ArrowUpRight size={14} />
                    </button>
                    {item.url && !item.sanitized_placeholder && (
                      <button
                        className="icon-button"
                        onClick={() => openLink(item.url)}
                      >
                        <ArrowUpRight size={17} />
                      </button>
                    )}
                    {item.path && (
                      <button
                        className="icon-button"
                        onClick={() =>
                          perform(() => bridge.download(item.id), "File saved.")
                        }
                      >
                        <Download size={17} />
                      </button>
                    )}
                  </div>
                </article>
              ))}
              {!visible.length && (
                <Empty
                  icon={Files}
                  title="A home for your resources"
                  text="Readable files and useful links will appear here."
                />
              )}
            </div>
          )}
          {page === "Replies" && (
            <div className="panel">
              {visible
                .filter((r) => r.state !== "resolved")
                .map((item) => (
                  <div className="request-row" key={item.id}>
                    <MessagesSquare size={22} />
                    <div className="row-main">
                      <strong>{item.title}</strong>
                      <small>{titleCase(item.state)}</small>
                    </div>
                    {item.source_link && (
                      <button
                        className="button"
                        onClick={() => openLink(item.source_link)}
                      >
                        Open Gmail <ArrowUpRight size={14} />
                      </button>
                    )}
                    <button
                      className="button"
                      onClick={() => feedback(item, "status", "resolved")}
                    >
                      Mark resolved
                    </button>
                  </div>
                ))}
              {!visible.some((r) => r.state !== "resolved") && (
                <Empty
                  icon={MessagesSquare}
                  title="Nothing needs a reply"
                  text="Direct requests will appear with their source conversation."
                />
              )}
            </div>
          )}
          {page === "Review" && (
            <div className="review-grid">
              {visible
                .filter((q) => ["open", "deferred"].includes(q.status))
                .slice(0, reviewLimit)
                .map((q) => (
                  <article className="panel review-card" key={q.id}>
                    <span className="eyebrow">
                      {q.status === "deferred"
                        ? "SAVED FOR LATER"
                        : "YOUR INPUT HELPS"}
                    </span>
                    <h3>{q.question}</h3>
                    {q.context?.reason && <p>{q.context.reason}</p>}
                    {q.context?.text && (
                      <blockquote>{q.context.text}</blockquote>
                    )}
                    <div className="review-actions">
                      {q.choices?.map((value) => (
                        <button
                          className="button"
                          key={String(value)}
                          onClick={() =>
                            mutate(
                              "/reviews/" + q.id + "/answer",
                              { value },
                              "Answer saved.",
                            )
                          }
                        >
                          {titleCase(String(value))}
                        </button>
                      ))}
                      {!q.choices?.length && q.field && (
                        <button
                          className="button primary"
                          onClick={() =>
                            setModal({ type: "answer", question: q })
                          }
                        >
                          Clarify
                        </button>
                      )}
                      {!q.field && (
                        <>
                          <button
                            className="button"
                            onClick={() => setPage("Profile")}
                          >
                            Review profile
                          </button>
                          <button
                            className="text-button"
                            onClick={() =>
                              mutate(
                                "/reviews/" + q.id + "/answer",
                                { value: "acknowledged" },
                                "Review recorded.",
                              )
                            }
                          >
                            Acknowledge
                          </button>
                        </>
                      )}
                      <button
                        className="text-button muted"
                        onClick={() =>
                          mutate(
                            "/reviews/" + q.id + "/answer",
                            { defer: true },
                            "Saved for later.",
                          )
                        }
                      >
                        Later
                      </button>
                      {q.record_id && (
                        <button
                          className="text-button"
                          onClick={() => source(q.record_id)}
                        >
                          See evidence <ArrowUpRight size={13} />
                        </button>
                      )}
                    </div>
                  </article>
                ))}
              {!visible.some((q) => q.status !== "answered") && (
                <Empty
                  icon={CheckCheck}
                  title="All caught up"
                  text="New questions will appear when a detail needs your judgment."
                />
              )}
              {visible.filter((q) => ["open", "deferred"].includes(q.status))
                .length > reviewLimit && (
                <button
                  className="button"
                  onClick={() => setReviewLimit(reviewLimit + 6)}
                >
                  Show six more questions <ArrowRight size={14} />
                </button>
              )}
            </div>
          )}
          {page === "Marks" && (
            <div className="panel table-panel">
              <table>
                <thead>
                  <tr>
                    <th>Course</th>
                    <th>Assessment</th>
                    <th>Your marks</th>
                    <th>Status</th>
                    <th>Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <strong>{r.course}</strong>
                      </td>
                      <td>{r.assessment}</td>
                      <td>
                        {r.earned === null ? "—" : `${r.earned} / ${r.maximum}`}
                      </td>
                      <td>
                        <span className="tag">
                          {titleCase(r.result_status)}
                        </span>
                      </td>
                      <td>
                        <button
                          className="text-button"
                          onClick={() => setModal({ type: "detail", item: r })}
                        >
                          View source <ArrowUpRight size={13} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!visible.length && (
                <Empty
                  icon={GraduationCap}
                  title="Your results, with context"
                  text="Confirm your roll number in Profile, then extract a result notice."
                />
              )}
              <div className="table-note">
                Totals are shown only when a confirmed grading scheme is
                available. Missing marks are never assumed to be zero.
              </div>
            </div>
          )}
          {page === "Profile" && (
            <div className="panel table-panel">
              <table>
                <thead>
                  <tr>
                    <th>Academic detail</th>
                    <th>Value</th>
                    <th>Evidence status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((f) => (
                    <tr key={f.id}>
                      <td>{titleCase(f.field)}</td>
                      <td>{String(f.value)}</td>
                      <td>
                        <span
                          className={
                            "tag " +
                            (f.status === "confirmed" ? "green" : "amber")
                          }
                        >
                          {titleCase(f.status)}
                        </span>
                      </td>
                      <td>
                        <button
                          className="text-button"
                          onClick={() => setModal({ type: "profile", item: f })}
                        >
                          Edit / confirm <ArrowUpRight size={13} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!visible.length && (
                <Empty
                  icon={UserRound}
                  title="Your academic context starts here"
                  text="We infer details from notices and ask when evidence is uncertain. You can add confirmed details yourself."
                />
              )}
            </div>
          )}
          {page === "Models" && (
            <>
              <div className="notice-box">
                <BrainCircuit size={20} />
                <div>
                  <strong>Self-trained, transparently evaluated.</strong>
                  <p>
                    Academic labels are provisional source annotations. These
                    scores measure agreement with those labels, not a
                    human-reviewed benchmark.
                  </p>
                </div>
              </div>
              {Object.entries(extra.models || {}).map(([task, report]) => (
                <section className="panel model-panel" key={task}>
                  <div className="section-title">
                    <div>
                      <span className="eyebrow">
                        {task === "academic"
                          ? "ACADEMIC NOTICE CLASSIFICATION"
                          : "SENTENCE ACTIONABILITY"}
                      </span>
                      <h2>
                        {report.records.toLocaleString()} labeled examples
                      </h2>
                    </div>
                    <span className="tag green">Grouped holdout</span>
                  </div>
                  <div className="model-bars">
                    {Object.entries(report.models).map(([name, score]) => (
                      <div className="model-bar" key={name}>
                        <strong>{titleCase(name)}</strong>
                        <div>
                          <i style={{ width: score.macro_f1 * 100 + "%" }} />
                        </div>
                        <span>
                          {score.macro_f1.toFixed(3)} <small>macro F1</small>
                        </span>
                      </div>
                    ))}
                  </div>
                  <p className="small-muted">
                    TF-IDF fits on training data only. Exact duplicates and
                    source groups stay in the same split. SVM is the predeclared
                    deployment model.
                  </p>
                </section>
              ))}
              {!Object.keys(extra.models || {}).length && (
                <Empty
                  icon={ChartNoAxesCombined}
                  title="No trained artifacts installed"
                  text="Run the documented training commands to create the model comparison."
                />
              )}
            </>
          )}
          {page === "Settings" && (
            <SettingsView
              extra={extra}
              perform={perform}
              mutate={mutate}
              refresh={refresh}
              importSchedule={importSchedule}
              setModal={setModal}
              flash={flash}
            />
          )}
        </div>
        <footer className="app-footer">
          <span>
            <ShieldCheck size={13} /> Your academic life. Your data.
          </span>
          <span>
            Always verify important deadlines against the official notice.
          </span>
        </footer>
      </main>
      {toast && (
        <div className="toast">
          <Check size={17} />
          {toast}
        </div>
      )}
      {modal && (
        <ModalView
          modal={modal}
          close={() => setModal(null)}
          mutate={mutate}
          perform={perform}
          source={source}
          openLink={openLink}
          feedback={feedback}
          refresh={refresh}
          setModal={setModal}
          timezone={dashboard?.timezone || "Asia/Kolkata"}
        />
      )}
    </div>
  );
}

function Importance({ item, onChange }) {
  return (
    <select
      aria-label={`Importance for ${item.title}`}
      className={"importance " + (item.importance || "medium")}
      value={item.importance || "medium"}
      onChange={(e) => onChange(item, "importance", e.target.value)}
    >
      <option value="high">High priority</option>
      <option value="medium">Medium</option>
      <option value="low">Low priority</option>
    </select>
  );
}
function Empty({ icon: Icon, title, text }) {
  return (
    <div className="empty-state">
      <span>
        <Icon size={27} />
      </span>
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}

function SettingsView({
  extra,
  perform,
  mutate,
  refresh,
  importSchedule,
  setModal,
  flash,
}) {
  const [settings, setSettings] = useState(extra.settings || {});
  useEffect(() => setSettings(extra.settings || {}), [extra.settings]);
  return (
    <div className="settings-layout">
      <section className="panel settings-panel">
        <h2>Connected accounts</h2>
        <p>Connect only the services you want. Mail access is read-only.</p>
        {["gmail", "calendar"].map((service) => (
          <div className="service-card" key={service}>
            <span
              className={
                "stat-icon " + (service === "gmail" ? "peach" : "blue")
              }
            >
              {service === "gmail" ? (
                <Mail size={23} />
              ) : (
                <CalendarDays size={23} />
              )}
            </span>
            <div className="row-main">
              <strong>
                {service === "gmail" ? "Gmail" : "Google Calendar"}
              </strong>
              <small>
                {extra.connections?.[service]?.connected
                  ? "Connected"
                  : extra.connections?.[service]?.error || "Not connected"}
              </small>
            </div>
            {extra.connections?.[service]?.connected ? (
              <>
                <button
                  className="button"
                  onClick={() =>
                    mutate(
                      "/connections/" + service + "/sync",
                      {},
                      "Sync queued.",
                    )
                  }
                >
                  Sync now
                </button>
                <button
                  className="text-button"
                  onClick={() =>
                    perform(async () => {
                      await request("/connections/" + service, "DELETE");
                      refresh();
                    })
                  }
                >
                  Disconnect
                </button>
              </>
            ) : (
              <button
                className="button"
                onClick={() =>
                  perform(async () => {
                    const result = await bridge.connect(service);
                    if (result) {
                      flash(
                        "Sign-in queued. Complete Google sign-in in your browser.",
                      );
                      refresh();
                    }
                  })
                }
              >
                Connect <ArrowUpRight size={14} />
              </button>
            )}
          </div>
        ))}
        <p className="small-muted">
          Choose a Google Desktop OAuth client JSON when connecting. Tokens are
          stored in your operating system credential vault. Calendar access is
          optional.
        </p>
      </section>
      <section className="panel settings-panel">
        <h2>Use what you already collected</h2>
        <p>
          Import the scoped, anonymized mail collection. Re-importing updates
          the same records.
        </p>
        <button
          className="button primary"
          onClick={() =>
            mutate(
              "/dataset/import",
              { collection: "scoped" },
              "Dataset import queued. You can keep using the app.",
            )
          }
        >
          <Inbox size={16} /> Import scoped mail dataset
        </button>
        <div className="settings-divider" />
        <h3>Academic schedule</h3>
        <div className="button-group">
          <button
            className="button"
            onClick={() => importSchedule("timetable")}
          >
            Timetable JSON
          </button>
          <button className="button" onClick={() => importSchedule("holidays")}>
            Holiday JSON
          </button>
        </div>
      </section>
      <section className="panel settings-panel">
        <h2>Your defaults</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            perform(async () => {
              await request("/settings", "PUT", settings);
              flash("Settings saved.");
              refresh();
            });
          }}
        >
          <label>
            Timezone
            <input
              value={settings.timezone || "Asia/Kolkata"}
              onChange={(e) =>
                setSettings({ ...settings, timezone: e.target.value })
              }
            />
          </label>
          <label>
            Sync interval (minutes)
            <input
              type="number"
              min="5"
              max="1440"
              value={settings.sync_minutes || 10}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  sync_minutes: Number(e.target.value),
                })
              }
            />
          </label>
          <label>
            Gmail labels (comma separated; empty means all authorized labels)
            <input
              value={(settings.gmail_labels || []).join(", ")}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  gmail_labels: e.target.value
                    .split(",")
                    .map((x) => x.trim())
                    .filter(Boolean),
                })
              }
            />
          </label>
          <label>
            Optional sender filters (comma separated)
            <input
              value={(settings.senders || []).join(", ")}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  senders: e.target.value
                    .split(",")
                    .map((x) => x.trim())
                    .filter(Boolean),
                })
              }
            />
          </label>
          <button className="button primary">Save defaults</button>
        </form>
        <div className="settings-divider" />
        <h3>Personal learning</h3>
        <p>
          Acceptances and corrections stay in this profile. They do not train
          the shared classifier.
        </p>
        <button
          className="button"
          onClick={() =>
            mutate(
              "/preferences/reset",
              {},
              "Personal preference history reset.",
            )
          }
        >
          Reset learned preferences
        </button>
      </section>
      <section className="panel settings-panel">
        <h2>Optional AI wording</h2>
        <p>
          Local briefings work without an API. When you request enhanced
          wording, selected upcoming facts are sent to your configured provider.
        </p>
        <button
          className="button"
          onClick={() =>
            perform(async () => {
              const r = await bridge.configureSummary();
              if (r)
                flash(
                  "Provider configured. Request enhancement from the weekly briefing.",
                );
            })
          }
        >
          Choose provider configuration JSON
        </button>
        <p className="small-muted">
          The JSON needs endpoint, model, and api_key. The key goes to the OS
          credential vault and never enters this interface.
        </p>
      </section>
      <section className="panel settings-panel">
        <h2>Background activity</h2>
        {extra.jobs?.length ? (
          extra.jobs.map((job) => (
            <div className="job-row" key={job.id}>
              <div>
                <strong>{titleCase(job.task)}</strong>
                <small>{job.error || niceDate(job.updated_at)}</small>
              </div>
              <span
                className={"tag " + (job.status === "failed" ? "amber" : "")}
              >
                {job.status}
              </span>
            </div>
          ))
        ) : (
          <p className="small-muted">No background jobs yet.</p>
        )}
      </section>
    </div>
  );
}

function ModalView({
  modal,
  close,
  mutate,
  perform,
  source,
  openLink,
  feedback,
  refresh,
  setModal,
  timezone,
}) {
  const [form, setForm] = useState({
      subject: "",
      text: "",
      course: "",
      assessment: "",
      json: "",
      field: modal.item?.field || "roll_number",
      value: modal.item?.value ?? "",
      title: "",
      start: "",
      end: "",
      flexible: true,
      role: "event_start",
    }),
    [preview, setPreview] = useState(null),
    [localError, setLocalError] = useState("");
  const set = (key, value) => setForm((v) => ({ ...v, [key]: value }));
  const execute = async (fn) => {
    setLocalError("");
    try {
      await fn();
    } catch (e) {
      setLocalError(e.message);
    }
  };
  const submit = async (e) => {
    e.preventDefault();
    await execute(async () => {
      let result;
      if (modal.type === "notice")
        result = await mutate(
          "/ingest",
          { subject: form.subject, text: form.text },
          "Notice analyzed.",
        );
      if (modal.type === "marks")
        result = await mutate(
          "/marks/extract",
          { course: form.course, assessment: form.assessment, text: form.text },
          "Result processed. Check Review for ambiguity.",
        );
      if (modal.type === "profile") {
        if (modal.item)
          result = await feedback(modal.item, "value", form.value);
        else
          result = await mutate(
            "/profile/facts",
            {
              field: form.field,
              value: form.field.startsWith("enrollment:") ? true : form.value,
            },
            "Academic detail confirmed.",
          );
      }
      if (modal.type === "block")
        result = await mutate(
          "/calendar/items",
          {
            title: form.title,
            start: form.start,
            end: form.end,
            flexible: form.flexible,
          },
          "Personal block added.",
        );
      if (modal.type === "answer")
        result = await mutate(
          "/reviews/" + modal.question.id + "/answer",
          {
            value:
              modal.question.field === "date"
                ? { date: form.value, role: form.role }
                : form.value,
          },
          "Clarification saved.",
        );
      if (result) close();
    });
  };
  const title = {
    notice: "Analyze a notice",
    marks: "Extract your results",
    profile: "Your academic detail",
    schedule:
      modal.kind === "timetable"
        ? "Import your timetable"
        : "Import holiday list",
    block: "Plan a personal block",
    detail:
      modal.item?.title ||
      modal.item?.filename ||
      modal.item?.subject ||
      "Source detail",
    proposal: "Review suggested change",
    answer: "Clarify this detail",
    summary: "Your weekly briefing",
    notifications: "Your notifications",
  }[modal.type];
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="modal-heading">
          <h2>{title}</h2>
          <button
            className="icon-button"
            onClick={close}
            aria-label="Close dialog"
          >
            <X size={20} />
          </button>
        </div>
        {localError && <div className="error">{localError}</div>}
        {["notice", "marks", "profile", "block", "answer"].includes(
          modal.type,
        ) && (
          <form onSubmit={submit}>
            {modal.type === "notice" && (
              <label>
                Subject
                <input
                  value={form.subject}
                  onChange={(e) => set("subject", e.target.value)}
                  placeholder="Course / notice subject"
                />
              </label>
            )}
            {modal.type === "marks" && (
              <>
                <div className="two-fields">
                  <label>
                    Course code
                    <input
                      value={form.course}
                      onChange={(e) => set("course", e.target.value)}
                      placeholder="NLP201"
                      required
                    />
                  </label>
                  <label>
                    Assessment
                    <input
                      value={form.assessment}
                      onChange={(e) => set("assessment", e.target.value)}
                      placeholder="Midsem / Quiz 1"
                      required
                    />
                  </label>
                </div>
                <p className="small-muted">
                  A confirmed roll number is required. Ambiguous rows are sent
                  for review.
                </p>
                <button
                  type="button"
                  className="button"
                  onClick={() =>
                    perform(async () => {
                      const r = await bridge.upload();
                      if (r) set("text", r.text || "");
                    })
                  }
                >
                  <Upload size={15} /> Read a result file
                </button>
              </>
            )}
            {["notice", "marks"].includes(modal.type) && (
              <label>
                {modal.type === "marks"
                  ? "Result text or table"
                  : "Original notice text"}
                <textarea
                  rows="10"
                  value={form.text}
                  onChange={(e) => set("text", e.target.value)}
                  required
                  placeholder="Paste the original text here…"
                />
              </label>
            )}
            {modal.type === "profile" && (
              <>
                <label>
                  Field
                  <input
                    value={form.field}
                    onChange={(e) => set("field", e.target.value)}
                    disabled={!!modal.item}
                    placeholder="roll_number, program, semester, enrollment:NLP201"
                  />
                </label>
                <label>
                  Confirmed value
                  <input
                    value={String(form.value)}
                    onChange={(e) => set("value", e.target.value)}
                    required
                  />
                </label>
              </>
            )}
            {modal.type === "block" && (
              <>
                <label>
                  What are you planning?
                  <input
                    value={form.title}
                    onChange={(e) => set("title", e.target.value)}
                    required
                  />
                </label>
                <div className="two-fields">
                  <label>
                    Start
                    <input
                      type="datetime-local"
                      value={form.start}
                      onChange={(e) => set("start", e.target.value)}
                      required
                    />
                  </label>
                  <label>
                    End
                    <input
                      type="datetime-local"
                      value={form.end}
                      onChange={(e) => set("end", e.target.value)}
                      required
                    />
                  </label>
                </div>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={form.flexible}
                    onChange={(e) => set("flexible", e.target.checked)}
                  />
                  This block can move, after my approval
                </label>
              </>
            )}
            {modal.type === "answer" && (
              <>
                <p>{modal.question.question}</p>
                <label>
                  Your answer
                  <input
                    type={modal.question.field === "date" ? "date" : "text"}
                    value={form.value}
                    onChange={(e) => set("value", e.target.value)}
                    required
                  />
                </label>
                {modal.question.field === "date" && (
                  <label>
                    Date role
                    <select
                      value={form.role}
                      onChange={(e) => set("role", e.target.value)}
                    >
                      {[
                        "event_start",
                        "exam_date",
                        "assignment_deadline",
                        "registration_deadline",
                        "publication_date",
                        "other",
                      ].map((r) => (
                        <option key={r} value={r}>
                          {titleCase(r)}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </>
            )}
            <button className="button primary wide">
              {modal.type === "profile"
                ? "Confirm detail"
                : modal.type === "marks"
                  ? "Find my result"
                  : modal.type === "block"
                    ? "Add personal block"
                    : modal.type === "answer"
                      ? "Save answer"
                      : "Analyze notice"}{" "}
              <ArrowRight size={16} />
            </button>
          </form>
        )}
        {modal.type === "schedule" && (
          <>
            <p>
              Use the prepared prompt with an external AI. It must clarify batch
              choices and unclear entries before producing your personal JSON.
            </p>
            <button
              className="button"
              onClick={() =>
                execute(async () => {
                  const p = await request("/prompts/" + modal.kind);
                  setModal({
                    type: "detail",
                    item: {
                      title: "External AI import prompt",
                      text: p.prompt,
                    },
                  });
                })
              }
            >
              <FileText size={15} /> Get the external AI prompt
            </button>
            <label>
              JSON from your external AI
              <textarea
                rows="11"
                value={form.json}
                onChange={(e) => {
                  set("json", e.target.value);
                  setPreview(null);
                }}
                placeholder="Paste schema-valid JSON…"
              />
            </label>
            <div className="button-group">
              <button
                className="button"
                onClick={() =>
                  perform(async () => {
                    const data = await bridge.chooseJson(modal.kind);
                    if (data) {
                      set("json", JSON.stringify(data, null, 2));
                      setPreview(null);
                    }
                  })
                }
              >
                Choose JSON file
              </button>
              <button
                className="button primary"
                onClick={() =>
                  execute(async () => {
                    const result = await request(
                      "/imports/" + modal.kind,
                      "POST",
                      { data: JSON.parse(form.json), confirm: false },
                    );
                    setPreview(result);
                  })
                }
              >
                Validate & preview
              </button>
            </div>
            {preview && (
              <div className="import-preview">
                <h3>Review before activating</h3>
                {preview.sessions ? (
                  <>
                    <p>
                      {preview.term_start} → {preview.term_end} ·{" "}
                      {JSON.stringify(preview.student_context)}
                    </p>
                    {preview.sessions.map((s, i) => (
                      <div className="preview-row" key={i}>
                        <strong>{s.course}</strong>
                        <span>
                          {
                            ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][
                              s.weekday
                            ]
                          }{" "}
                          {s.start}–{s.end}
                        </span>
                      </div>
                    ))}
                  </>
                ) : (
                  preview.holidays.map((h, i) => (
                    <div className="preview-row" key={i}>
                      <strong>{h.name}</strong>
                      <span>
                        {h.date}
                        {h.end_date ? " → " + h.end_date : ""}
                      </span>
                    </div>
                  ))
                )}
                <button
                  className="button primary wide"
                  onClick={async () => {
                    const result = await mutate(
                      "/imports/" + modal.kind,
                      { data: preview, confirm: true },
                      "Schedule activated.",
                    );
                    if (result) close();
                  }}
                >
                  Confirm and activate
                </button>
              </div>
            )}
          </>
        )}
        {modal.type === "detail" && (
          <>
            <div className="detail-meta">
              {modal.item.course && (
                <span className="tag">{modal.item.course}</span>
              )}
              {modal.item.status && (
                <span className="tag">{titleCase(modal.item.status)}</span>
              )}
              {modal.item.date_precision === "date" && (
                <span className="tag amber">Time unspecified</span>
              )}
            </div>
            <pre className="source-text">
              {modal.item.text ||
                modal.item.description ||
                modal.item.evidence?.text ||
                (modal.item.field
                  ? titleCase(modal.item.field) +
                    ": " +
                    String(modal.item.value)
                  : "No readable source text is available. Check the related resources or the original notice.")}
            </pre>
            {modal.item.url && !modal.item.sanitized_placeholder && (
              <button
                className="button"
                onClick={() => openLink(modal.item.url)}
              >
                Open resource <ArrowUpRight size={15} />
              </button>
            )}
            {modal.item.path && (
              <button
                className="button"
                onClick={() =>
                  perform(() => bridge.download(modal.item.id), "File saved.")
                }
              >
                Save original <Download size={15} />
              </button>
            )}
            {modal.item.evidence_ids?.length > 0 && (
              <>
                <h3>Source evidence</h3>
                <div className="evidence-list">
                  {modal.item.evidence_ids.map((id, i) => (
                    <button
                      className="button"
                      key={id}
                      onClick={() => source(id)}
                    >
                      Source {i + 1} <ArrowUpRight size={13} />
                    </button>
                  ))}
                </div>
              </>
            )}
            {(modal.item.resource_ids || modal.item.attachment_resource_ids)
              ?.length > 0 && (
              <>
                <h3>Related resources</h3>
                <div className="evidence-list">
                  {(
                    modal.item.resource_ids ||
                    modal.item.attachment_resource_ids
                  ).map((id, i) => (
                    <button
                      className="button"
                      key={id}
                      onClick={() => source(id)}
                    >
                      Resource {i + 1} <FileText size={13} />
                    </button>
                  ))}
                </div>
              </>
            )}
          </>
        )}
        {modal.type === "proposal" && (
          <>
            <p>{modal.item.explanation}</p>
            <div className="proposal-time">
              <CalendarDays />
              <strong>
                {new Date(modal.item.start).toLocaleString("en-IN", {
                  timeZone: timezone,
                })}
              </strong>
              <span>
                until{" "}
                {new Date(modal.item.end).toLocaleTimeString("en-IN", {
                  timeZone: timezone,
                })}
              </span>
            </div>
            <p className="small-muted">
              Nothing has moved yet. Availability is checked again when you
              approve.
            </p>
            <button
              className="button primary wide"
              onClick={async () => {
                const r = await mutate(
                  "/proposals/" + modal.item.id + "/approve",
                  {},
                  "Change approved.",
                );
                if (r) close();
              }}
            >
              Approve this change <Check size={16} />
            </button>
          </>
        )}
        {modal.type === "summary" && (
          <>
            <button
              className="button"
              onClick={() =>
                execute(async () => {
                  const report = await request("/summary/enhance", "POST", {});
                  setModal({ type: "summary", report });
                })
              }
            >
              <BrainCircuit size={15} /> Enhance wording with configured API
            </button>
            <p className="muted">
              Upcoming commitments and actions, linked to the underlying
              records.
            </p>
            {modal.report?.items?.length ? (
              modal.report.items.map((item) => (
                <div className="summary-item" key={item.id}>
                  <strong>{item.summary}</strong>
                  {modal.report.method === "api_assisted" && (
                    <p className="small-muted">
                      {item.title} · {item.date || "Reply pending"}
                    </p>
                  )}
                  <div>
                    {item.evidence_ids.map((id, i) => (
                      <button
                        className="text-button"
                        key={id}
                        onClick={() => source(id)}
                      >
                        Source {i + 1}
                      </button>
                    ))}
                  </div>
                </div>
              ))
            ) : (
              <Empty
                icon={Sun}
                title="A quiet week ahead"
                text="No confirmed items in this window. Unresolved items remain in Review."
              />
            )}
          </>
        )}
        {modal.type === "notifications" && (
          <>
            <button
              className="button"
              onClick={async () => {
                await mutate(
                  "/notifications/read",
                  {},
                  "Notifications marked read.",
                );
                close();
              }}
            >
              Mark all read
            </button>
            {modal.rows?.length ? (
              modal.rows
                .slice()
                .reverse()
                .map((n) => (
                  <div className="summary-item" key={n.id}>
                    <strong>{n.title}</strong>
                    <p>
                      {niceDate(n.date)}
                      {n.time_unspecified ? " · Time unspecified" : ""}
                    </p>
                    <button
                      className="text-button"
                      onClick={() => source(n.record_id)}
                    >
                      View item
                    </button>
                  </div>
                ))
            ) : (
              <Empty
                icon={Bell}
                title="No reminders yet"
                text="Confirmed upcoming obligations will generate in-app reminders while the app is running."
              />
            )}
          </>
        )}
      </section>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
