import React, { useEffect, useState, useCallback } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const GENRES = ['All', 'Action', 'Sci-Fi', 'Drama', 'Animation', 'Comedy', 'Thriller', 'Romance', 'Horror'];
const img = (p, s = 'w500') => (p ? (p.startsWith('http') ? p : `https://image.tmdb.org/t/p/${s}${p}`) : '');

// Cinema & Popcorn Themed Fallback Poster for movies without images
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

function App() {
  const [rows, setRows] = useState([]);
  const [featured, setFeatured] = useState(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [movie, setMovie] = useState(null);
  const [list, setList] = useState([]);
  const [page, setPage] = useState('home');
  const [activeGenre, setActiveGenre] = useState('All');
  const [about, setAbout] = useState(false);
  const [notice, setNotice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [metrics, setMetrics] = useState(null);  // full report: {catalogue, model, metrics}

  // Helper to extract movie ID from URL pathname or search params
  const getMovieIdFromUrl = useCallback(() => {
    const pathMatch = window.location.pathname.match(/\/movie\/(\d+)/);
    if (pathMatch) return parseInt(pathMatch[1], 10);
    const params = new URLSearchParams(window.location.search);
    const mParam = params.get('movie');
    if (mParam) return parseInt(mParam, 10);
    return null;
  }, []);

  // Fetch full details and recommendations for a given movie ID
  const loadMovieById = useCallback(async (id, initialData = null) => {
    if (initialData) {
      setMovie({ ...initialData, loadingDetails: true });
    } else {
      setMovie({ id, title: 'Loading film...', loadingDetails: true });
    }
    setQuery(''); // Clear search so detail view is visible immediately
    setPage('detail');
    window.scrollTo({ top: 0, behavior: 'smooth' });

    try {
      const resp = await fetch('/api/movie/' + id);
      if (resp.ok) {
        const d = await resp.json();
        setMovie({ ...d.movie, recommendations: d.recommendations || [], loadingDetails: false });
      } else {
        setMovie((prev) => (prev ? { ...prev, loadingDetails: false } : null));
      }
    } catch {
      setMovie((prev) => (prev ? { ...prev, loadingDetails: false } : null));
    }
  }, []);

  // Initial load: parse catalogue and check if URL points directly to a movie
  useEffect(() => {
    // Ensure back button on home stays on home
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

    fetch('/api/metrics?k=10')
      .then((r) => r.json())
      .then((d) => setMetrics(d.metrics || null))
      .catch(() => {});

    // Browser Refresh / Direct Link handling: check if opened on a movie URL
    const initialMovieId = getMovieIdFromUrl();
    if (initialMovieId) {
      loadMovieById(initialMovieId);
    }
  }, [getMovieIdFromUrl, loadMovieById]);

  // Handle Browser Back and Forward Buttons (popstate)
  useEffect(() => {
    const handlePopState = () => {
      const id = getMovieIdFromUrl();
      if (id) {
        loadMovieById(id);
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
      200
    );
    return () => {
      clearTimeout(t);
      c.abort();
    };
  }, [query]);

  // Open movie card with browser history update
  const openMovie = (m) => {
    setQuery(''); // Clear search so search results overlay does not block movie page
    if (window.location.pathname !== `/movie/${m.id}`) {
      window.history.pushState({ movieId: m.id }, '', `/movie/${m.id}`);
    }
    loadMovieById(m.id, m);
  };

  // Return to home view
  const goHome = () => {
    setMovie(null);
    setPage('home');
    setQuery('');
    setActiveGenre('All');
    if (window.location.pathname !== '/') {
      window.history.pushState({ page: 'home' }, '', '/');
    }
  };

  const toggleList = async (m) => {
    try {
      const d = await (await fetch('/api/my-list/' + m.id, { method: 'POST' })).json();
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

  const poster = (m) => img(m.poster_url || m.poster_path, 'w342');
  const back = (m) => img(m.backdrop_url || m.backdrop_path, 'w1280') || poster(m);

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
            <Card key={m.id} m={m} showMatch={showMatch} />
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
      <header className="nav">
        <button className="brand" onClick={goHome}>
          CINEPHILE
        </button>
        <nav>
          <button onClick={goHome} className={page === 'home' && !movie && !query ? 'selected' : ''}>
            Home
          </button>
          <button
            onClick={() => {
              setPage('list');
              setMovie(null);
              setQuery('');
              if (window.location.pathname !== '/my-list') {
                window.history.pushState({ page: 'list' }, '', '/my-list');
              }
            }}
            className={page === 'list' && !movie ? 'selected' : ''}
          >
            My List <span className="count">{list.length}</span>
          </button>
          <button onClick={() => setAbout(true)}>Model & About</button>
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

      {/* Genre Filter Chips */}
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

      {/* Detail View has highest precedence if movie is selected */}
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
          <div className="detail-body">
            <div className="detail-poster">
              {poster(movie) ? (
                <img src={poster(movie)} alt={movie.title + ' poster'} onError={(e) => (e.currentTarget.style.display = 'none')} />
              ) : (
                <CinemaFallback title={movie.title} year={movie.year} />
              )}
            </div>
            <div>
              <p className="eyebrow">CINEPHILE PICK</p>
              <h1>{movie.title}</h1>
              <div className="meta">
                <span className="green">
                  {movie.rating ? '★ ' + Number(movie.rating).toFixed(1) : 'Not rated'}
                </span>
                <span>{movie.year}</span>
                {movie.runtime && <span>{movie.runtime} min</span>}
                <span>{movie.genres?.join(' · ')}</span>
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
                {list.some((x) => x.id === movie.id)
                  ? '✓ In My List (Remove)'
                  : '+ Add to My List'}
              </button>
            </div>
          </div>

          {!movie.loadingDetails && movie.recommendations?.length > 0 && (
            <section className="recommend">
              <div className="row-head">
                <h2>More like this (Explainable AI Recommendations)</h2>
                <span>Ranked by TF-IDF & Bayesian similarity</span>
              </div>
              <div className="scroller">
                {movie.recommendations.map((m) => (
                  <Card key={m.id} m={m} showMatch={true} />
                ))}
              </div>
            </section>
          )}
        </main>
      ) : query.trim() ? (
        <main className="search-page">
          <p className="eyebrow">DISCOVERY</p>
          <div className="search-title">
            <h1>Search results</h1>
            <span>{results.length} matches</span>
          </div>
          {results.length ? (
            <div className="grid">
              {results.map((m) => (
                <Card key={m.id} m={m} />
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
      ) : (
        <>
          {page === 'home' && featured && activeGenre === 'All' && (
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
                    {featured.rating ? Number(featured.rating).toFixed(1) + ' / 10' : 'Featured'}
                  </span>
                  <span>{featured.year}</span>
                  <span>{featured.genres?.slice(0, 2).join(' · ')}</span>
                </div>
                <p className="hero-overview">{featured.overview}</p>
                <div className="actions">
                  <button className="primary" onClick={() => openMovie(featured)}>
                    View details
                  </button>
                  <button className="secondary" onClick={() => toggleList(featured)}>
                    {list.some((x) => x.id === featured.id) ? 'Remove from My List' : 'Add to My List'}
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
              (page === 'list' ? [{ title: 'My List', movies: list }] : filteredRows)
                .filter((r) => r.movies?.length)
                .map((r, i) => (
                  <Row key={r.title + i} r={r} showMatch={r.title === 'Picked for you'} />
                ))
            )}

            {page === 'list' && !list.length && (
              <div className="empty">
                <h2>Your list starts here</h2>
                <p>Save films you want to watch and they will appear here to power your recommendations.</p>
                <button className="primary" onClick={goHome}>
                  Explore films
                </button>
              </div>
            )}
          </main>
        </>
      )}

      <footer>
        <b>CINEPHILE</b>
        <span>designed by Ayush (friendly neighborhood engineer)</span>
        <button onClick={() => setAbout(true)}>Model & Evaluation Metrics</button>
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
            <button className="close" onClick={() => setAbout(false)}>✕ Close</button>

            <p className="eyebrow">ML MODEL & EVALUATION</p>
            <h2 id="about-title">CinePhile — Recommendation System</h2>
            <p className="about-desc">
              Content-based filtering using <strong>TF-IDF</strong> + <strong>Cosine Similarity</strong>, blended with Bayesian
              vote-confidence rating. The vectorizer is fit on the <strong>training set only</strong> — the test set is never seen
              during training (no data leakage).
            </p>

            {metrics?.catalogue ? (
              <>
                <div className="about-section-label">DATASET &amp; TRAIN / TEST SPLIT</div>
                <div className="split-bar-wrap">
                  <div className="split-bar">
                    <div className="split-train" style={{width: metrics.catalogue.train_pct + '%'}}>
                      Train — {metrics.catalogue.train.toLocaleString()} films ({metrics.catalogue.train_pct}%)
                    </div>
                    <div className="split-test" style={{width: metrics.catalogue.test_pct + '%'}}>
                      Test — {metrics.catalogue.test} ({metrics.catalogue.test_pct}%)
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
                      <td>Relevant films ranked near the top of the list</td>
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

            <p className="legal">
              This product uses the TMDB API for film metadata and artwork. Not endorsed by TMDB.
            </p>
            <button className="primary" onClick={() => setAbout(false)}>Back to browsing</button>
          </section>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
