from crm.fcrm.doctype.crm_deal.crm_deal import CRMDeal
from crm.fcrm.doctype.crm_lead.crm_lead import CRMLead

from team_access.realtime import PrivateUpdate


class ActivityLead(PrivateUpdate, CRMLead):
    no_feed_on_delete = True


class ActivityDeal(PrivateUpdate, CRMDeal):
    no_feed_on_delete = True
