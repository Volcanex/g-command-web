# Jobs

`/jobs`, under Projects. The unchanged `new-view.py` scaffold was run in a
temporary staging directory while the Projects group was pending; only this
page was copied into the worktree. `tabs: projects` joins that group's rail.

Six native views. Interviews is the default: one card per opportunity from
g-jobs' `data/interviews.yaml`, its rounds joined from the brain calendar by
company word (each linking to `/calendar?item=<slug>&date=<date>`), and the
crossed-off ones collapsed below. Then daytime tap, applications and record
detail, cover letters, screening questions, and the last eight runs with pacing
and event detail. `?view=applications&application=<stem>` opens an archived
record directly.

`api.py` runs g-jobs' existing `gjobs.site.data` readers with its service's
`/usr/bin/python3` from the sibling `g-jobs` checkout (`GJOBS_DIR` overrides it).
Those readers resolve letters, answers, outcomes and pacing. Reads are fresh,
uncached and read-only. Every endpoint checks Command's `cookie_ok`, including
CV downloads; the original reader validates archive membership and this route
also confines the result to `out/variants`.

The one write is `POST /api/jobs/interviews/<id>` (status, next step, a note).
It runs `gjobs interview set` and commits `data/interviews.yaml`, both as
gabriel through `runuser`, so the checkout never gains root-owned files; gsync
pushes the commit. It answers with the fresh interviews view.

Keep PageHead, Loaded, Empty, the shell gutter and transition. The page-specific
view-contract check is `python3 /home/gabriel/g-levels/glevels/viewcontract.py . --page jobs`.
