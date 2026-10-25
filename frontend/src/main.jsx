import React, { useEffect, useState, useCallback } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const GENRES = ['All', 'Action', 'Sci-Fi', 'Drama', 'Animation', 'Comedy', 'Thriller', 'Romance', 'Horror'];

// Safe TMDB image URL builder handling null, undefined, relative, and absolute paths
const cleanImgUrl = (p, size = 'w500') => {
  if (!p || typeof p !== 'string') return '';
  const trimmed = p.trim();
  if (!trimmed || trimmed === 'null' || trimmed === 'undefined' || trimmed === 'None') return '';
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) return trimmed;
  const path = trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
  return `https://image.tmdb.org/t/p/${size}${path}`;
};

const poster = (m) => (m ? cleanImgUrl(m.poster_url || m.poster_path, 'w342') : '');
const back = (m) => (m ? cleanImgUrl(m.backdrop_url || m.backdrop_path, 'w1280') || poster(m) : '');

// Cinema & Popcorn Themed SVG Fallback Poster (No Emojis)
function CinemaFallback({ title, year }) {
  return (
    <div className="fallback-poster" aria-hidden="true">
      <svg className="popcorn-icon" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M18 24L22 56H42L46 24H18Z" fill="#e50914" />
        <path d="M22 24L24 56M32 24V56M42 24L40 56" stroke="#ffffff" strokeWidth="2" strokeLinecap="round" />
        <circle cx="24" cy="20" r="5" fill="#f5c518" />
        <circle cx="32" cy="17" r="6" fill="#f5f5f5" />
        <circle cx="40" cy="20" r="5" fill="#f5c518" />
        <circle cx="20" cy="23" r="4" fill="#f5f5f5" />
        <circle cx="44" cy="23" r="4" fill="#f5f5f5" />
        <circle cx="28" cy="21" r="4" fill="#f5c518" />
        <circle cx="36" cy="21" r="4" fill="#f5c518" />
      </svg>
      <div className="fallback-text">
        <span className="fallback-tag">CINEMA</span>
        <b>{title}</b>
        <small>{year || '—'}</small>
      </div>
    </div>
  );
}

// Crisp Vector Icons (Replaces all emojis)
const IconStar = () => (
  <svg className="icon-svg" viewBox="0 0 24 24" width="13" height="13" fill="#f5c518" aria-hidden="true" style={{ verticalAlign: '-1px', marginRight: '4px' }}>
    <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z" />
  </svg>
);

const IconCheck = () => (
  <svg className="icon-svg" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ verticalAlign: '-2px', marginRight: '5px' }}>
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const IconPlus = () => (
  <svg className="icon-svg" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ verticalAlign: '-2px', marginRight: '5px' }}>
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
  </svg>
);

const IconClose = () => (
  <svg className="icon-svg" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ verticalAlign: '-1px', marginRight: '4px' }}>
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

function App() {
  const [rows, setRows] = useState([]);
  const [featured, setFeatured] = useState(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [movie, setMovie] = useState(null);
  const [list, setList] = useState([]);
  const [page, setPage] = useState('home'); // 'home' | 'list' | 'detail' | 'search'
  const [activeGenre, setActiveGenre] = useState('All');
  const [about, setAbout] = useState(false);
  const [notice, setNotice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [metrics, setMetrics] = useState(null);

  const getMovieIdFromUrl = useCallback(() => {
    const pathMatch = window.location.pathname.match(/\/movie\/(\d+)/);
    if (pathMatch) return parseInt(pathMatch[1], 10);
    const params = new URLSearchParams(window.location.search);
    const mParam = params.get('movie');
    if (mParam) return parseInt(mParam, 10);
    return null;
  }, []);

  const loadMovieById = useCallback(async (id, initialData = null) => {
    if (initialData) {
      setMovie({ ...initialData, loadingDetails: true, error: false });
    } else {
      setMovie({ id, title: 'Loading film details...', loadingDetails: true, error: false });
    }
    setQuery('');
    setPage('detail');
    window.scrollTo({ top: 0, behavior: 'smooth' });

    try {
      const resp = await fetch('/api/movie/' + id);
      if (resp.ok) {
        const d = await resp.json();
        setMovie({ ...d.movie, recommendations: d.recommendations || [], loadingDetails: false, error: false });
      } else {
        setMovie((prev) => (prev ? { ...prev, loadingDetails: false, error: true } : { id, error: true }));
      }
    } catch {
      setMovie((prev) => (prev ? { ...prev, loadingDetails: false, error: true } : { id, error: true }));
    }
  }, []);

  const fetchMetrics = useCallback(() => {
    fetch('/api/metrics?k=10')
      .then((r) => r.json())
      .then((d) => {
        if (d && d.catalogue && d.metrics) {
          setMetrics(d);
        }
      })
      .catch(() => {});
  }, []);

  const openAboutModal = () => {
    setAbout(true);
    fetchMetrics();
  };

  // Initial Boot
  useEffect(() => {
    if (!window.history.state) {
      window.history.replaceState({ page: 'home' }, '', window.location.pathname + window.location.search);
    }

    fetch('/api/home')
      .then((r) => r.json())
      .then((d) => {
        setRows(d.rows || []);
        setFeatured(d.featured || null);
        setList(d.my_list || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));

    fetchMetrics();

    const initialMovieId = getMovieIdFromUrl();
    if (initialMovieId) {
      loadMovieById(initialMovieId);
    }
  }, [getMovieIdFromUrl, loadMovieById, fetchMetrics]);

  // Handle Browser Back and Forward Buttons (popstate)
  useEffect(() => {
    const handlePopState = () => {
      const id = getMovieIdFromUrl();
      if (id) {
        loadMovieById(id);
      } else if (window.location.pathname === '/my-list') {
        setMovie(null);
        setPage('list');
        setQuery('');
      } else {
        setMovie(null);
        setPage('home');
        setQuery('');
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [getMovieIdFromUrl, loadMovieById]);

  // Live debounced search
  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    const c = new AbortController();
    const t = setTimeout(
      () =>
        fetch('/api/search?q=' + encodeURIComponent(query) + '&limit=30', { signal: c.signal })
          .then((r) => r.json())
          .then((d) => setResults(d.results || []))
          .catch(() => {}),
      220
    );
    return () => {
      clearTimeout(t);
      c.abort();
    };
  }, [query]);

  const openMovie = (m) => {
    const targetId = m.tmdb_id || m.id;
    setQuery('');
    if (window.location.pathname !== `/movie/${targetId}`) {
      window.history.pushState({ movieId: targetId }, '', `/movie/${targetId}`);
    }
    loadMovieById(targetId, m);
  };

  const goHome = () => {
    setMovie(null);
    setPage('home');
    setQuery('');
    setActiveGenre('All');
    if (window.location.pathname !== '/') {
      window.history.pushState({ page: 'home' }, '', '/');
    }
  };

  const goMyList = () => {
    setMovie(null);
    setPage('list');
    setQuery('');
    if (window.location.pathname !== '/my-list') {
      window.history.pushState({ page: 'list' }, '', '/my-list');
    }
  };

  const toggleList = async (m) => {
    const targetId = m.id || m.tmdb_id;
    try {
      const d = await (await fetch('/api/my-list/' + targetId, { method: 'POST' })).json();
      if (d.in_list) {
        setList((old) => [...old.filter((x) => x.id !== m.id), m]);
        setNotice({ text: `Added "${m.title}" to My List` });
      } else {
        setList((old) => old.filter((x) => x.id !== m.id));
        setNotice({
          text: `Removed "${m.title}" from My List`,
          undoAction: () => toggleList(m),
        });
      }
      setTimeout(() => setNotice(null), 3000);
    } catch {
      setNotice({ text: 'Could not update My List' });
      setTimeout(() => setNotice(null), 2500);
    }
  };

  function Card({ m, showMatch = false }) {
    const [imgFailed, setImgFailed] = useState(false);
    const posterSrc = poster(m);

    return (
      <button className="card" onClick={() => openMovie(m)} aria-label={'View ' + m.title}>
        <div className="poster">
          {showMatch && m.match_pct && (
            <div className="match-badge">{m.match_pct}% Match</div>
          )}
          {posterSrc && !imgFailed ? (
            <img
              loading="lazy"
              src={posterSrc}
              alt={m.title + ' poster'}
              onError={() => setImgFailed(true)}
            />
          ) : (
            <CinemaFallback title={m.title} year={m.year} />
          )}
          <div className="card-hover">
            <b>{m.title}</b>
            <small>
              {m.year || '—'} · {m.rating ? Number(m.rating).toFixed(1) : 'NR'}
              {m.similarity > 0 && <span className="sim-raw"> · {m.similarity}</span>}
            </small>
            {m.shared_reasons && m.shared_reasons.length > 0 && (
              <span className="shared-tag">
                {m.shared_reasons.slice(0, 2).join(' · ')}
              </span>
            )}
          </div>
        </div>
      </button>
    );
  }

  function Row({ r, showMatch = false }) {
    return (
      <section className="row">
        <div className="row-head">
          <h2>{r.title}</h2>
          <span>{r.movies?.length || 0} titles</span>
        </div>
        <div className="scroller">
          {(r.movies || []).map((m) => (
            <Card key={m.id || m.tmdb_id} m={m} showMatch={showMatch} />
          ))}
        </div>
      </section>
    );
  }

  const filteredRows =
    activeGenre === 'All'
      ? rows
      : rows.filter((r) => r.title.toLowerCase().includes(activeGenre.toLowerCase()));

  return (
    <div className="app">
      {/* Full Page Initial Loader */}
      {loading && (
        <div className="page-loader-overlay" role="status">
          <div className="cinema-spinner"></div>
          <p>Loading CinePhile Catalogue…</p>
        </div>
      )}

      {/* Navigation Bar */}
      <header className="nav">
        <button className="brand" onClick={goHome}>
          CINEPHILE
        </button>
        <nav>
          <button onClick={goHome} className={page === 'home' && !movie && !query ? 'selected' : ''}>
            Home
          </button>
          <button onClick={goMyList} className={page === 'list' && !movie ? 'selected' : ''}>
            My List <span className="count">{list.length}</span>
          </button>
          <button onClick={openAboutModal}>Model & About</button>
        </nav>
        <div className="search">
          <input
            aria-label="Search movies"
            placeholder="Search titles, directors, genres…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage('search');
              setMovie(null);
            }}
          />
          <span>/</span>
        </div>
      </header>

      {/* Genre Filter Chips (Home Only) */}
      {!movie && !query && page === 'home' && (
        <div className="genre-bar" role="tablist" aria-label="Genre filters">
          {GENRES.map((g) => (
            <button
              key={g}
              className={`chip ${activeGenre === g ? 'active' : ''}`}
              onClick={() => setActiveGenre(g)}
              role="tab"
              aria-selected={activeGenre === g}
            >
              {g}
            </button>
          ))}
        </div>
      )}

      {/* 1. Detail View: High Precedence */}
      {movie ? (
        <main className="detail">
          <div
            className="detail-bg"
            style={{
              backgroundImage: `linear-gradient(90deg,#080808 0%,rgba(8,8,8,.86) 43%,rgba(8,8,8,.18)),linear-gradient(0deg,#080808,transparent 65%),url("${back(
                movie
              )}")`,
            }}
          />
          <button className="back" onClick={goHome}>
            ← Back to browsing
          </button>

          {movie.error ? (
            <div className="empty-list-card" style={{ maxWidth: '600px', margin: '40px auto' }}>
              <h2>Film Not Found</h2>
              <p>We couldn't retrieve the details for this title.</p>
              <button className="primary" onClick={goHome}>
                Back to browsing
              </button>
            </div>
          ) : movie.loadingDetails ? (
            <div className="detail-skeleton" aria-label="Loading movie details">
              <div className="skeleton-card" style={{ height: '380px' }}></div>
              <div className="detail-skeleton-copy">
                <div className="skeleton-line title"></div>
                <div className="skeleton-line meta"></div>
                <div className="skeleton-line desc"></div>
                <div className="skeleton-line desc short"></div>
              </div>
            </div>
          ) : (
            <>
              <div className="detail-body">
                <div className="detail-poster">
                  {poster(movie) ? (
                    <img
                      src={poster(movie)}
                      alt={movie.title + ' poster'}
                      onError={(e) => {
                        e.currentTarget.style.display = 'none';
                        const fb = e.currentTarget.parentElement.querySelector('.fallback-poster');
                        if (fb) fb.style.display = 'flex';
                      }}
                    />
                  ) : null}
                  <div style={{ display: poster(movie) ? 'none' : 'flex', height: '100%' }}>
                    <CinemaFallback title={movie.title} year={movie.year} />
                  </div>
                </div>
                <div>
                  <p className="eyebrow">CINEPHILE PICK</p>
                  <h1>{movie.title}</h1>
                  <div className="meta">
                    <span className="green">
                      {movie.rating ? (
                        <>
                          <IconStar />
                          {Number(movie.rating).toFixed(1)}
                        </>
                      ) : (
                        'Not rated'
                      )}
                    </span>
                    <span>{movie.year}</span>
                    {movie.runtime && <span>{movie.runtime} min</span>}
                    <span>{Array.isArray(movie.genres) ? movie.genres.join(' · ') : movie.genres}</span>
                  </div>
                  <p className="overview">
                    {movie.overview || 'A synopsis is not available for this title yet.'}
                  </p>
                  {movie.director && (
                    <p className="detail-line">
                      <b>Director</b>
                      {movie.director}
                    </p>
                  )}
                  {movie.cast?.length > 0 && (
                    <p className="detail-line">
                      <b>Cast</b>
                      {Array.isArray(movie.cast) ? movie.cast.join(', ') : movie.cast}
                    </p>
                  )}
                  <button className="primary" onClick={() => toggleList(movie)}>
                    {list.some((x) => x.id === movie.id || (movie.tmdb_id && x.tmdb_id === movie.tmdb_id)) ? (
                      <>
                        <IconCheck />
                        In My List (Remove)
                      </>
                    ) : (
                      <>
                        <IconPlus />
                        Add to My List
                      </>
                    )}
                  </button>
                </div>
              </div>

              {movie.recommendations?.length > 0 && (
                <section className="recommend">
                  <div className="row-head">
                    <h2>More like this (Content-Based Filtering)</h2>
                    <span>Ranked by TF-IDF &amp; Cosine Alignment</span>
                  </div>
                  <div className="scroller">
                    {movie.recommendations.map((m) => (
                      <Card key={m.id || m.tmdb_id} m={m} showMatch={true} />
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
        </main>
      ) : query.trim() ? (
        /* 2. Search Results View */
        <main className="search-page">
          <p className="eyebrow">DISCOVERY</p>
          <div className="search-title">
            <h1>Search results</h1>
            <span>{results.length} matches</span>
          </div>
          {results.length ? (
            <div className="grid">
              {results.map((m) => (
                <Card key={m.id || m.tmdb_id} m={m} />
              ))}
            </div>
          ) : (
            <div className="empty">
              {query.length < 2
                ? 'Keep typing to search the catalogue.'
                : 'No films found. Try another title, actor, or genre.'}
            </div>
          )}
        </main>
      ) : page === 'list' ? (
        /* 3. Dedicated My List View (HCI: Clean Hierarchy, No Component Overlap) */
        <main className="list-page">
          <div className="list-header-banner">
            <div>
              <p className="eyebrow">YOUR COLLECTION</p>
              <h1>My List</h1>
              <p className="list-subtitle">
                Films you've saved to watch. Every title in your list actively guides your personalized recommendation profile.
              </p>
            </div>
            <div className="list-count-badge">
              <b>{list.length}</b>
              <span>{list.length === 1 ? 'film saved' : 'films saved'}</span>
            </div>
          </div>

          {list.length > 0 ? (
            <>
              <div className="grid">
                {list.map((m) => (
                  <div key={m.id || m.tmdb_id} className="list-item-card">
                    <Card m={m} />
                    <button
                      className="remove-from-list-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleList(m);
                      }}
                      title="Remove from My List"
                    >
                      <IconClose />
                      Remove
                    </button>
                  </div>
                ))}
              </div>

              {/* Personalized Picks Rail directly beneath Watchlist */}
              {rows.find((r) => r.title === 'Picked for you')?.movies?.length > 0 && (
                <div className="list-recs-wrap">
                  <div className="row-head">
                    <h2>Picked for you based on your list</h2>
                    <span>Personalized Profile Centroid · Content-Based Similarity</span>
                  </div>
                  <div className="scroller">
                    {rows.find((r) => r.title === 'Picked for you').movies.map((m) => (
                      <Card key={m.id || m.tmdb_id} m={m} showMatch={true} />
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="empty-list-card">
              <div className="empty-cinema-art">
                <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
                  <rect x="8" y="16" width="48" height="36" rx="4" stroke="#666" strokeWidth="2" />
                  <circle cx="22" cy="34" r="6" stroke="#e50914" strokeWidth="2" />
                  <circle cx="42" cy="34" r="6" stroke="#e50914" strokeWidth="2" />
                  <path d="M8 26H56" stroke="#444" strokeWidth="1.5" />
                </svg>
              </div>
              <h2>Your Watchlist is Empty</h2>
              <p>Save films you want to watch. Your choices actively guide your personalized recommendation engine.</p>
              <button className="primary" onClick={goHome}>
                Browse Films
              </button>
            </div>
          )}
        </main>
      ) : (
        /* 4. Home Page View */
        <>
          {featured && activeGenre === 'All' && (
            <section
              className="hero"
              style={{
                backgroundImage: `linear-gradient(90deg,#080808 0%,rgba(8,8,8,.8) 42%,rgba(8,8,8,.08)),linear-gradient(0deg,#080808,transparent 52%),url("${back(
                  featured
                )}")`,
              }}
            >
              <div className="hero-copy">
                <p className="eyebrow">FEATURED FILM</p>
                <h1>{featured.title}</h1>
                <div className="meta">
                  <span className="green">
                    {featured.rating ? (
                      <>
                        <IconStar />
                        {Number(featured.rating).toFixed(1)} / 10
                      </>
                    ) : (
                      'Featured'
                    )}
                  </span>
                  <span>{featured.year}</span>
                  <span>{Array.isArray(featured.genres) ? featured.genres.slice(0, 2).join(' · ') : featured.genres}</span>
                </div>
                <p className="hero-overview">{featured.overview}</p>
                <div className="actions">
                  <button className="primary" onClick={() => openMovie(featured)}>
                    View details
                  </button>
                  <button className="secondary" onClick={() => toggleList(featured)}>
                    {list.some((x) => x.id === featured.id || (featured.tmdb_id && x.tmdb_id === featured.tmdb_id))
                      ? 'Remove from My List'
                      : 'Add to My List'}
                  </button>
                </div>
              </div>
              <div className="hero-tag">CURATED FOR YOUR NEXT MOVIE NIGHT</div>
            </section>
          )}

          <main className="content">
            {loading ? (
              <div className="skeleton-rows" aria-label="Loading movies">
                <div className="skeleton-row">
                  {[...Array(6)].map((_, i) => (
                    <div key={i} className="skeleton-card" />
                  ))}
                </div>
                <div className="skeleton-row">
                  {[...Array(6)].map((_, i) => (
                    <div key={i} className="skeleton-card" />
                  ))}
                </div>
              </div>
            ) : (
              filteredRows
                .filter((r) => r.movies?.length)
                .map((r, i) => (
                  <Row key={r.title + i} r={r} showMatch={r.title === 'Picked for you'} />
                ))
            )}
          </main>
        </>
      )}

      {/* Footer */}
      <footer>
        <b>CINEPHILE</b>
        <span>designed by Ayush (friendly neighborhood engineer)</span>
        <button onClick={openAboutModal}>Model &amp; Evaluation Metrics</button>
      </footer>

      {/* Interactive Toast with Undo */}
      {notice && (
        <div className="toast" role="status">
          <span>{notice.text}</span>
          {notice.undoAction && <button onClick={notice.undoAction}>Undo</button>}
        </div>
      )}

      {/* Modal Dialog with Live ML Metrics */}
      {about && (
        <div className="overlay" onClick={() => setAbout(false)}>
          <section
            className="about"
            role="dialog"
            aria-modal="true"
            aria-labelledby="about-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button className="close" onClick={() => setAbout(false)}>
              <IconClose />
              Close
            </button>
            <p className="eyebrow">ML MODEL &amp; EVALUATION</p>
            <h2 id="about-title">CinePhile — Recommendation System</h2>
            <p className="about-desc">
              Content-based filtering using <strong>TF-IDF</strong> + <strong>Cosine Similarity</strong>, blended with Bayesian
              vote-confidence rating. The vectorizer is fit on the <strong>training set only</strong> — the test set is never seen
              during training (no data leakage).
            </p>

            {/* Train / Test Split Breakdown */}
            {metrics?.catalogue ? (
              <>
                <div className="about-section-label">DATASET &amp; TRAIN / TEST SPLIT</div>
                <div className="split-bar-wrap">
                  <div className="split-bar">
                    <div className="split-train" style={{ width: metrics.catalogue.train_pct + '%' }}>
                      Train — {metrics.catalogue.train.toLocaleString()} films ({metrics.catalogue.train_pct}%)
                    </div>
                    <div className="split-test" style={{ width: metrics.catalogue.test_pct + '%' }}>
                      Test — {metrics.catalogue.test.toLocaleString()} ({metrics.catalogue.test_pct}%)
                    </div>
                  </div>
                </div>
                <div className="about-stat-row">
                  <div className="about-stat">
                    <span>{metrics.catalogue.total.toLocaleString()}</span>
                    <small>Total in catalogue</small>
                  </div>
                  <div className="about-stat">
                    <span>{metrics.catalogue.train.toLocaleString()}</span>
                    <small>Training set</small>
                  </div>
                  <div className="about-stat">
                    <span>{metrics.catalogue.test.toLocaleString()}</span>
                    <small>Test set</small>
                  </div>
                  <div className="about-stat">
                    <span>{metrics.model?.features?.toLocaleString()}</span>
                    <small>TF-IDF features</small>
                  </div>
                </div>
              </>
            ) : (
              <div className="about-loading">Loading model stats…</div>
            )}

            {/* Evaluation Metrics Table */}
            {metrics?.metrics ? (
              <>
                <div className="about-section-label">
                  EVALUATION METRICS — TEST SET &nbsp;
                  <span className="about-k-badge">K = {metrics.metrics.k}</span>
                  &nbsp;·&nbsp; {metrics.metrics.num_test_queries} queries evaluated
                </div>
                <table className="metrics-table">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>Score</th>
                      <th>What it measures</th>
                      <th>Priority</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="metric-primary">
                      <td><b>Accuracy (Hit Rate @ {metrics.metrics.k})</b></td>
                      <td><span className="metric-pill green">{(metrics.metrics.accuracy_at_k * 100).toFixed(2)}%</span></td>
                      <td>Whether relevant movies are successfully recommended in top {metrics.metrics.k}</td>
                      <td><span className="priority high">High</span></td>
                    </tr>
                    <tr className="metric-primary">
                      <td><b>Precision @ {metrics.metrics.k}</b></td>
                      <td><span className="metric-pill green">{(metrics.metrics.precision_at_k * 100).toFixed(2)}%</span></td>
                      <td>How many of the top {metrics.metrics.k} recs are relevant</td>
                      <td><span className="priority high">High</span></td>
                    </tr>
                    <tr className="metric-primary">
                      <td><b>Recall @ {metrics.metrics.k}</b></td>
                      <td><span className="metric-pill green">{(metrics.metrics.recall_at_k * 100).toFixed(2)}%</span></td>
                      <td>Fraction of all relevant films retrieved</td>
                      <td><span className="priority high">High</span></td>
                    </tr>
                    <tr className="metric-primary">
                      <td><b>NDCG @ {metrics.metrics.k}</b></td>
                      <td><span className="metric-pill green">{metrics.metrics.ndcg_at_k.toFixed(4)}</span></td>
                      <td>Whether relevant movies appear near the top of the ranked list</td>
                      <td><span className="priority high">High</span></td>
                    </tr>
                    <tr>
                      <td><b>Coverage</b></td>
                      <td><span className="metric-pill">{metrics.metrics.catalogue_coverage_pct}%</span></td>
                      <td>% of catalogue reachable via recommendations</td>
                      <td><span className="priority med">Medium</span></td>
                    </tr>
                    <tr>
                      <td><b>Diversity</b></td>
                      <td><span className="metric-pill">{metrics.metrics.intra_list_diversity}</span></td>
                      <td>Mean pairwise dissimilarity within a rec list</td>
                      <td><span className="priority med">Medium</span></td>
                    </tr>
                    <tr>
                      <td><b>Explainability</b></td>
                      <td><span className="metric-pill">{metrics.metrics.explainability_pct}%</span></td>
                      <td>Recs sharing ≥1 attribute (genre/director/cast/keyword)</td>
                      <td><span className="priority med">Medium</span></td>
                    </tr>
                  </tbody>
                </table>
              </>
            ) : (
              <div className="about-loading">Computing evaluation metrics…</div>
            )}

            {/* Baseline Comparison */}
            {metrics?.baselines && (
              <>
                <div className="about-section-label" style={{ marginTop: '20px' }}>
                  BENCHMARK BASELINE COMPARISONS (TOP-10)
                </div>
                <table className="metrics-table">
                  <thead>
                    <tr>
                      <th>Model / Baseline</th>
                      <th>Precision @ 10</th>
                      <th>NDCG @ 10</th>
                      <th>Hit Rate @ 10</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.values(metrics.baselines).map((b, idx) => (
                      <tr key={idx} className={b.name.includes("Proposed") ? "metric-primary" : ""}>
                        <td><b>{b.name}</b></td>
                        <td><span className={`metric-pill ${b.name.includes("Proposed") ? "green" : ""}`}>{(b.precision_at_10 * 100).toFixed(1)}%</span></td>
                        <td><span className={`metric-pill ${b.name.includes("Proposed") ? "green" : ""}`}>{b.ndcg_at_10.toFixed(4)}</span></td>
                        <td><span className={`metric-pill ${b.name.includes("Proposed") ? "green" : ""}`}>{(b.hit_rate_at_10 * 100).toFixed(1)}%</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}

            {/* Model Limitations Notice */}
            <div style={{ marginTop: '20px', padding: '12px 14px', background: '#1c1c1c', border: '1px solid #333', borderRadius: '4px', fontSize: '12px', color: '#aaa', lineHeight: '1.6' }}>
              <strong style={{ color: '#fff', display: 'block', marginBottom: '4px' }}>Model Limitations &amp; Task Scope:</strong>
              CinePhile operates as an Information Retrieval ranking engine rather than a discrete classifier. Similarity scores quantify feature vector alignment in the weighted TF-IDF space, not discrete accuracy or subjective user satisfaction ratings.
            </div>

            <p className="legal">
              This product uses the TMDB API for film metadata and artwork. Not endorsed by TMDB.
            </p>
            <button className="primary" onClick={() => setAbout(false)}>
              Back to browsing
            </button>
          </section>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
