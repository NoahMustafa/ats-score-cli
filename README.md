# ATS Score CLI

Terminal tool that scores a resume for ATS-readiness, writing quality, and (optionally) match against a job description. Fully offline, ships as a single self-contained binary per OS.

```
ats-score resume.pdf                 # ATS + content + writing
ats-score resume.pdf --jd job.txt    # + JD match
ats-score resume.pdf --json          # machine-readable output
```

See [specs.md](specs.md) for design and [tasks.md](tasks.md) for build status.
