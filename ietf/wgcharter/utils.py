from django.conf import settings
import re

from datetime import datetime
from ietf.group.models import GroupEvent, ChangeStateGroupEvent
from ietf.doc.models import Document, DocAlias, DocHistory, RelatedDocument, DocumentAuthor, DocEvent
from ietf.utils.history import find_history_active_at

def set_or_create_charter(wg):
    try:
        charter = Document.objects.get(docalias__name="charter-ietf-%s" % wg.acronym)
    except Document.DoesNotExist:
        charter = Document.objects.create(
            name="charter-ietf-" + wg.acronym,
            time=datetime.now(),
            type_id="charter",
            title=wg.name,
            group=wg,
            abstract=wg.name,
            rev="",
            )
        # Create an alias as well
        DocAlias.objects.create(
            name=charter.name,
            document=charter
            )
    if wg.charter != charter:
        wg.charter = charter
        wg.save()
    return charter

def add_wg_comment(request, wg, text, ballot=None):
    if request:
        login = request.user.get_profile()
    else:
        login = None

    e = GroupEvent(group=wg, type="added_comment", by=login)
    e.desc = text
    e.save()

def log_state_changed(request, doc, by, prev_state):
    e = DocEvent(doc=doc, by=by)
    e.type = "changed_document"
    e.desc = u"State changed to <b>%s</b> from %s" % (
        doc.get_state().name,
        prev_state.name if prev_state else "None")
    e.save()
    return e

def log_group_state_changed(request, wg, by, note=''):
    e = ChangeStateGroupEvent(group=wg, by=by, type="changed_state")
    e.state = wg.state
    e.desc = { 'active': "Started group",
               'propose': "Proposed group",
               'conclude': "Concluded group",
               }[wg.state_id]

    if note:
        e.desc += "<br>%s" % note

    e.save()
    return e

def get_charter_for_revision(charter, r):
    if r == None:
        return None
    else:
        l = list(charter.history_set.filter(rev=r).order_by('-time'))
        if l != []:
            return l[0]
        else:
            # Get the lastest history entry
            l = list(charter.history_set.all().order_by('-time'))
            if l != []:
                class FakeHistory(object):
                    def __init__(self, name, rev, time):
                        self.name = name
                        self.rev = rev
                        self.time = time

                return FakeHistory(l[0].name, charter.rev, charter.time)
            else:
                # no history, just return charter
                return charter

def get_group_for_revision(wg, r):
    if r == None:
        return None
    else:
        l = list(wg.charter.history_set.filter(rev=r).order_by('-time'))
        if l != []:
            o = list(wg.history_set.filter(time__lte=l[0].time).order_by('-time'))
            if o != []:
                return o[0]
            else:
                return wg
        else:
            return wg

def prev_revision(rev):
    m = re.match(r"(?P<major>[0-9][0-9])(-(?P<minor>[0-9][0-9]))?", rev)
    if m.group('minor') and m.group('minor') != "00":
        return "%s-%#02d" % (m.group('major'), int(m.group('minor')) - 1)
    else:
        return None

def next_revision(rev):
    if rev == "":
        return "00-00"
    m = re.match(r"(?P<major>[0-9][0-9])(-(?P<minor>[0-9][0-9]))?", rev)
    if m.group('minor'):
        return "%s-%#02d" % (m.group('major'), int(m.group('minor')) + 1)
    else:
        return "%s-00" % (m.group('major'))

def approved_revision(rev):
    if rev == "":
        return ""
    m = re.match(r"(?P<major>[0-9][0-9])(-(?P<minor>[0-9][0-9]))?", rev)
    return m.group('major')

def next_approved_revision(rev):
    if rev == "":
        return "01"
    m = re.match(r"(?P<major>[0-9][0-9])(-(?P<minor>[0-9][0-9]))?", rev)
    return "%#02d" % (int(m.group('major')) + 1)

def update_telechat(request, doc, by, new_telechat_date):
    # FIXME: fix auto-setting returning item problem and reuse
    # function in idrfc/utils.py instead of this one
    from ietf.doc.models import TelechatDocEvent
    
    on_agenda = bool(new_telechat_date)

    prev = doc.latest_event(TelechatDocEvent, type="scheduled_for_telechat")
    prev_telechat = prev.telechat_date if prev else None
    prev_agenda = bool(prev_telechat)
    
    e = TelechatDocEvent()
    e.type = "scheduled_for_telechat"
    e.by = by
    e.doc = doc
    e.telechat_date = new_telechat_date
    
    if on_agenda != prev_agenda:
        if on_agenda:
            e.desc = "Placed on agenda for telechat - %s" % new_telechat_date
        else:
            e.desc = "Removed from agenda for telechat"
        e.save()
    elif on_agenda and new_telechat_date != prev_telechat:
        e.desc = "Telechat date has been changed to <b>%s</b> from <b>%s</b>" % (new_telechat_date, prev_telechat)
        e.save()
