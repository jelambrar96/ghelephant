from json_objects import *
import orjson
import logging


class JSONToCSVConverter:
    def __init__(self, writers) -> None:
        self.writers = writers
        self.added_ids = set()
        self.added_pushes = set()
        self.added_issues = set()
        self.added_prs = set()

    def write_events(self, f):
        for line in reversed(f.readlines()):
            try:
                generic_event = msgspec.json.decode(line, type=GenericEvent)
            except msgspec.ValidationError:
                logging.error(f"Malformed event: {line}")
                continue

            if generic_event.id in self.added_ids:
                continue
            else:
                self.added_ids.add(generic_event.id)

            match generic_event.type:
                case 'PushEvent':
                    record = msgspec.json.decode(line, type=PushEvent)
                    if record.payload.push_id in self.added_pushes:
                        continue
                    else:
                        self.added_pushes.add(record.payload.push_id)
                    self.write_push_event(record, generic_event)
                case 'CommitCommentEvent':
                    self.write_commit_comment_event(line, generic_event)
                case 'WatchEvent':
                    self.write_generic_event(generic_event)
                case 'ReleaseEvent':
                    self.write_release_event(line, generic_event)
                case 'DeleteEvent':
                    self.write_delete_event(line, generic_event)
                case 'GollumEvent':
                    self.write_gollum_event(line, generic_event)
                case 'PublicEvent':
                    self.write_generic_event(generic_event)
                case 'MemberEvent':
                    self.write_member_event(line, generic_event)
                case 'ForkEvent':
                    self.write_fork_event(line, generic_event)
                case 'CreateEvent':
                    self.write_create_event(line, generic_event)
                case 'IssuesEvent':
                    self.write_issues_event(line, generic_event)
                case 'IssueCommentEvent':
                    self.write_issue_comment_event(line, generic_event)
                case 'PullRequestEvent':
                    self.write_pull_request_event(line, generic_event)
                case 'PullRequestReviewEvent':
                    self.write_pull_request_review_event(line, generic_event)
                case 'PullRequestReviewCommentEvent':
                    self.write_pull_request_review_comment_event(line, generic_event)
                case _:
                    logging.error(f'Unknown event type: {generic_event.type}')

    def write_pull_request_tuple(self, pr, action):
        if pr.id in self.added_prs:
            return
        else:
            self.added_prs.add(pr.id)
        assignee = pr.assignee.id if pr.assignee else None
        assignees = [a.id for a in pr.assignees] if pr.assignees else None
        requested_reviewers = [r.id for r in pr.requested_reviewers] if pr.requested_reviewers else None
        requested_teams = [t.name for t in pr.requested_teams] if pr.requested_teams else None
        milestone = pr.milestone.id if pr.milestone else None
        labels = [l.name for l in pr.labels] if pr.labels else None
        head_repo = pr.head.repo.id if pr.head.repo else None
        base_repo = pr.base.repo.id if pr.base.repo else None

        self.writers.pullrequest.writerow((pr.id, action, pr.number, pr.state, pr.locked, pr.title,
                pr.user.login, pr.user.id, pr.user.type, pr.user.site_admin, pr.body,
                pr.created_at, pr.updated_at, pr.closed_at, pr.merged_at, pr.merge_commit_sha, assignee, assignees, 
                str(requested_reviewers)[:255], str(requested_teams)[:255], labels, milestone, pr.draft, pr.author_association,
                pr.active_lock_reason, pr.merged, pr.mergeable, pr.mergeable_state, pr.merged_by.id if pr.merged_by else None,
                pr.comments, pr.review_comments, pr.maintainer_can_modify, pr.commits, pr.additions, pr.deletions, pr.changed_files,
                head_repo, pr.head.sha, base_repo, pr.base.sha))

    def write_pull_request_review_comment_event(self, line: bytes, generic_event: GenericEvent):
        record = orjson.loads(line)
        record_msgspec = msgspec.json.decode(line, type=PullRequestReviewCommentEvent)
        self.writers.archive.writerow(self.generic_event_tuple(generic_event, record['payload']['comment']['id']))
        c = record['payload']['comment']
        self.writers.pullrequestreviewcomment.writerow((c['id'], c.get('pull_request_review_id'),
                                                        c['diff_hunk'], c['path'], c['position'],
                                                        c['original_position'], c['commit_id'],
                                                        c['original_commit_id'], c['user']['id'],
                                                        c['user']['login'],
                                                        c['user']['type'], c['user']['site_admin'],
                                                        c['body'], c['created_at'], c['updated_at'],
                                                        c.get('author_association'), *self.reactions(c),
                                                        c.get('start_line'), c.get('original_start_line'),
                                                        c.get('start_side'), c.get('line'), c.get('original_line'),
                                                        c.get('side'), c.get('in_reply_to_id'),
                                                        record['payload']['pull_request']['id']))
        self.write_pull_request_tuple(record_msgspec.payload.pull_request, record_msgspec.payload.action)

    def write_pull_request_review_event(self, line: bytes, generic_event: GenericEvent):
        record = msgspec.json.decode(line, type=PullRequestReviewEvent)
        self.writers.archive.writerow(self.generic_event_tuple(generic_event, record.payload.review.id))
        p = record.payload.review
        self.writers.pullrequestreview.writerow((p.id, record.payload.action, p.user.id,
                                                p.user.login, p.user.type,
                                                p.user.site_admin, p.body, p.commit_id,
                                                p.submitted_at, p.state, p.author_association,
                                                record.payload.pull_request.id))
        self.write_pull_request_tuple(record.payload.pull_request, record.payload.action)

    def write_pull_request_event(self, line: bytes, generic_event: GenericEvent):
        record = msgspec.json.decode(line, type=PullRequestEvent)
        self.writers.archive.writerow(self.generic_event_tuple(generic_event, record.payload.pull_request.id))
        pr = record.payload.pull_request
        self.write_pull_request_tuple(pr, record.payload.action)

    def write_issue_comment_event(self, line: bytes, generic_event: GenericEvent):
        # TODO change to msgspec if no reactions shall be recorded
        record = orjson.loads(line)
        c = record['payload']['comment']
        comment_id = c['id']
        issue_id = record['payload']['issue']['id']

        self.writers.archive.writerow(self.generic_event_tuple(generic_event, comment_id))
        if issue_id not in self.added_issues:
            self.added_issues.add(issue_id)
            self.writers.issue.writerow(self.issue_event_tuple(record))
        app = c['performed_via_github_app']['slug'] if 'performed_via_github_app' in c and c['performed_via_github_app'] else None
        self.writers.issuecomment.writerow((comment_id, issue_id, c['user']['type'], c['user']['site_admin'],
                                            c['created_at'], c['updated_at'], c.get('author_association'), c['body'], app))

    def issue_event_tuple(self, record):
        i = record['payload']['issue']
        assignee = i.get('assignee')['id'] if i['assignee'] else None
        milestone = i['milestone']['id'] if i['milestone'] else None
        app = i['performed_via_github_app']['slug'] if 'performed_via_github_app' in i and i['performed_via_github_app'] else None
        assignees_ids = [a['id'] for a in i['assignees']] if 'assignees' in i else None
        labels_names = [l['name'] for l in i['labels']] if 'labels' in i else None
        return (record['payload']['action'], i['id'], i['number'], i['title'],
                i['user']['login'], i['user']['id'], i['user']['type'],
                i['user']['site_admin'], labels_names, i['state'], i['locked'], assignee, assignees_ids,
                milestone, i['comments'], i['created_at'], i['updated_at'], i['closed_at'],
                i.get('author_association'), i.get('active_lock_reason'), i.get('draft'), i.get('pull_request'), i['body'],
                *self.reactions(i), app, i.get('state_reason'))

    def write_issues_event(self, line: bytes, generic_event: GenericEvent):
        record = orjson.loads(line)
        issue_id = record['payload']['issue']['id']
        self.writers.archive.writerow(self.generic_event_tuple(generic_event, issue_id))
        if issue_id not in self.added_issues:
            self.added_issues.add(issue_id)
            self.writers.issue.writerow(self.issue_event_tuple(record))

    def write_create_event(self, line: bytes, generic_event: GenericEvent):
        record = msgspec.json.decode(line, type=CreateEvent)
        self.writers.archive.writerow(self.generic_event_tuple(generic_event))
        ref = record.payload.ref[:127] if record.payload.ref else None
        self.writers.createevent.writerow((generic_event.id, ref, record.payload.ref_type,
                                           record.payload.master_branch[:127], record.payload.description,
                                           record.payload.pusher_type))

    def write_fork_event(self, line: bytes, generic_event: GenericEvent):
        record = msgspec.json.decode(line, type=ForkEvent)
        f = record.payload.forkee
        license_key = f.license.key if f.license else None
        license_name = f.license.name if f.license else None
        license_spdx_id = f.license.spdx_id if f.license else None
        self.writers.archive.writerow(self.generic_event_tuple(generic_event, f.id))
        self.writers.forkevent.writerow((f.id, f.name, f.private, f.owner.id, f.owner.login,
                                         f.owner.type, f.owner.site_admin, f.description, f.fork,
                                         f.created_at,
                                         f.updated_at, f.pushed_at, f.homepage, f.size, f.stargazers_count,
                                         f.watchers_count,
                                         f.language, f.has_issues, f.has_projects, f.has_downloads, f.has_wiki,
                                         f.has_pages,
                                         f.forks_count, f.archived, f.disabled, f.open_issues_count, f.allow_forking,
                                         f.is_template, f.web_commit_signoff_required, f.topics, f.visibility, f.forks,
                                         f.open_issues, f.watchers,
                                         f.default_branch, f.public, license_key,
                                         license_name, license_spdx_id))

    def write_member_event(self, line: bytes, generic_event: GenericEvent):
        record = msgspec.json.decode(line, type=MemberEvent)
        self.writers.archive.writerow(self.generic_event_tuple(generic_event))
        self.writers.memberevent.writerow((generic_event.id, record.payload.member.id,
                                           record.payload.member.login,
                                           record.payload.member.type, record.payload.member.site_admin,
                                           record.payload.action))

    def write_gollum_event(self, line: bytes, generic_event: GenericEvent):
        record = msgspec.json.decode(line, type=GollumEvent)
        self.writers.archive.writerow(self.generic_event_tuple(generic_event))
        for page in record.payload.pages:
            self.writers.gollumevent.writerow(
                (generic_event.id, page.page_name[:255], page.title[:255], page.summary, page.action, page.sha))

    def write_delete_event(self, line: bytes, generic_event: GenericEvent):
        record = msgspec.json.decode(line, type=DeleteEvent)
        self.writers.archive.writerow(self.generic_event_tuple(generic_event))
        self.writers.deleteevent.writerow((generic_event.id, record.payload.ref[:255], record.payload.ref_type,
                                           record.payload.pusher_type))

    def write_release_event(self, line: bytes, generic_event: GenericEvent):
        record = msgspec.json.decode(line, type=ReleaseEvent)
        release = record.payload.release
        self.writers.archive.writerow(self.generic_event_tuple(generic_event, release.id))
        self.writers.releaseevent.writerow((release.id, release.tag_name,
                                            release.target_commitish, release.name[:255] if release.name else None, release.draft, release.prerelease,
                                            release.created_at, release.published_at, release.body))

    def write_push_event(self, record: PushEvent, generic_event: GenericEvent):
        self.writers.archive.writerow(self.generic_event_tuple(generic_event, record.payload.push_id))
        self.writers.pushevent.writerow((record.payload.push_id, record.payload.size,
                                         record.payload.distinct_size, record.payload.ref[:255],
                                         record.payload.head, record.payload.before))
        for commit in record.payload.commits:
            self.writers.commit.writerow((commit.sha, record.payload.push_id,
                                          commit.author.email[:127], commit.author.name[:127], commit.message,
                                          commit.distinct))

    def write_commit_comment_event(self, line: bytes, generic_event: GenericEvent):
        record = msgspec.json.decode(line, type=CommitCommentEvent)
        c = record.payload.comment
        self.writers.archive.writerow(self.generic_event_tuple(generic_event, c.id))
        self.writers.commitcommentevent.writerow((c.id, c.position, c.line,
                                                  c.path, c.commit_id, c.author_association, c.body))

    def write_generic_event(self, generic_event: GenericEvent):
        self.writers.archive.writerow(self.generic_event_tuple(generic_event))

    def reactions(self, record):
        reactions = record.get('reactions')
        if reactions:
            return reactions['total_count'], reactions['+1'], reactions['-1'], reactions['laugh'], reactions['hooray'], \
                   reactions['confused'], reactions['heart'], reactions['rocket'], reactions['eyes']
        return None, None, None, None, None, None, None, None, None

    def generic_event_tuple(self, record: GenericEvent, payload_id=None) -> tuple:
        org_id = record.org.id if record.org else None
        org_login = record.org.login if record.org else None
        return (record.id, record.type, record.actor.id, record.actor.login, record.repo.id,
                record.repo.name, payload_id, record.created_at,
                org_id, org_login)
