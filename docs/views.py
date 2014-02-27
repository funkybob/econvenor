from django.core.urlresolvers import reverse
from django.forms.models import inlineformset_factory
from django.forms import DateInput, HiddenInput, Textarea
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext

from accounts.models import Account
from decisions.models import Decision
from docs.forms import AgendaForm, MinutesForm
from docs.models import Item
from docs.pdfs import create_pdf_agenda
from docs.utils import add_item, \
                       calculate_meeting_duration, \
                       calculate_meeting_end_time, \
                       delete_item, \
                       distribute_agenda, \
                       find_preceding_meeting_date, \
                       get_formatted_meeting_duration, \
                       move_item, \
                       save_formset
from meetings.forms import MeetingForm
from meetings.models import Meeting
from participants.models import Participant
from tasks.models import Task
from utilities.commonutils import save_and_add_owner


def agenda_list(request):
    if not request.user.is_authenticated():
        return HttpResponseRedirect(reverse('index'))
    agendas = Meeting.objects.filter(owner=request.user).order_by('date')
    page_heading = 'Agendas'
    table_headings = ('Date', 'Description', 'Location',)
    return render_to_response('agenda_list.html', {'user': request.user, 'agendas': agendas, 'page_heading': page_heading, 'table_headings': table_headings}, RequestContext(request))


def agenda_edit(request, meeting_id):

    if not request.user.is_authenticated():
        return HttpResponseRedirect(reverse('index'))
    meeting = Meeting.objects.get(pk=int(meeting_id))
    if meeting.owner != request.user:
        return HttpResponseRedirect(reverse('index'))

    page_heading = 'Create agenda'
    task_list_headings = ('Description', 'Assigned to', 'Deadline')

    new_data_form = {}
    existing_data_forms = []
    existing_data_formset = {}
    editable_section = 'none'
    preceding_meeting_date = find_preceding_meeting_date(request.user, meeting_id)
    
    items = meeting.item_set.filter(owner=request.user).order_by('item_no')
        
    incomplete_task_list = Task.objects.filter(owner=request.user, status="Incomplete")
    completed_task_list = []
    if preceding_meeting_date != None:
        completed_task_list = Task.objects.filter(owner=request.user, status="Complete", deadline__gte=preceding_meeting_date).exclude(deadline__gte=meeting.date)
    account = Account.objects.filter(owner=request.user).last()

    # Management of meeting details
    if request.method == "POST":
        if 'edit_meeting_details_button' in request.POST:
            if request.POST['edit_meeting_details_button']=='edit_meeting_details':
                existing_data_forms = MeetingForm(instance=meeting, label_suffix='')
                editable_section = 'is_meeting_details'
        if 'save_meeting_details_button' in request.POST:
            if request.POST['save_meeting_details_button']=='save_meeting_details':
                new_data_form = MeetingForm(request.POST, instance=meeting, label_suffix='')
                if new_data_form.is_valid():
                    new_data_form.save()
                    editable_section = 'none'
        if 'cancel_meeting_details_button' in request.POST:
            if request.POST['cancel_meeting_details_button']=='cancel_meeting_details':
                editable_section = 'none'
        if 'delete_meeting_button' in request.POST:
            if request.POST['delete_meeting_button']=='delete_meeting':
                meeting.delete()
                return HttpResponseRedirect(reverse('agenda-list'))

    # Management of agenda items 
    if request.method == "POST":

        if 'save_items_button' in request.POST:
            if request.POST['save_items_button']=='save_items':
                save_formset(request, meeting, items, 'agenda')
                
        if 'add_item_button' in request.POST:
            if request.POST['add_item_button']=='add_item':
                add_item(request, meeting_id, items)
        
        if 'delete_button' in request.POST:
            delete_item(request, meeting_id)
        
        if 'down_button' in request.POST or 'up_button' in request.POST:
            move_item(request, meeting_id)
                          
        items = meeting.item_set.filter(owner=request.user).order_by('item_no')

    existing_data_forms = MeetingForm(instance=meeting, label_suffix='')
   
    item_formlist = []
    item_count = 0
    for item in items:
        item_count += 1
        item = AgendaForm(instance=item, prefix=item_count, label_suffix='')
        item_formlist.append(item)
    
    meeting_duration = get_formatted_meeting_duration(meeting_id)
    meeting_end_time = calculate_meeting_end_time(meeting_id)
        
    return render_to_response(
            'agenda_edit.html', {
                'user': request.user,
                'meeting_id': meeting_id,
                'meeting': meeting,
                'meeting_duration': meeting_duration,
                'meeting_end_time': meeting_end_time,
                'page_heading': page_heading,
                'task_list_headings': task_list_headings,
                'completed_task_list': completed_task_list,
                'incomplete_task_list': incomplete_task_list,
                'editable_section': editable_section,
                'items': items,
                'item_count': item_count,
                'existing_data_forms': existing_data_forms,
                'item_formlist': item_formlist,
                'new_data_form': new_data_form,
                'account': account
                },
            RequestContext(request)
        )




def agenda_distribute(request, meeting_id):
    if not request.user.is_authenticated():
        return HttpResponseRedirect(reverse('index'))
    meeting = Meeting.objects.get(pk=int(meeting_id))
    if meeting.owner != request.user:
        return HttpResponseRedirect(reverse('index'))
    if request.method == "POST":
        if 'agenda_distribute_button' in request.POST:
            if request.POST['agenda_distribute_button']=='distribute_agenda':
                pdf = create_pdf_agenda(request, meeting_id, 'attachment')
                distribute_agenda(request, meeting_id, pdf)
                return HttpResponseRedirect(reverse('agenda-sent', args=(meeting_id,)))
    else:
        task_list_headings = ('Description', 'Assigned to', 'Deadline')
        main_items = meeting.item_set.filter(owner=request.user, variety__exact='main')
        preliminary_items = meeting.item_set.filter(owner=request.user, variety__exact='preliminary')
        report_items = meeting.item_set.filter(owner=request.user, variety__exact='report')
        final_items = meeting.item_set.filter(owner=request.user, variety__exact='final')	
        incomplete_task_list = Task.objects.filter(owner=request.user, status="Incomplete")
        completed_task_list = Task.objects.filter(owner=request.user, status="Complete")
        participants = Participant.objects.filter(owner=request.user).order_by('first_name')
        meeting_duration = calculate_meeting_duration(meeting_id)
        account = Account.objects.filter(owner=request.user).last()
        return render_to_response('agenda_distribute.html', {'user': request.user, 'meeting_id': meeting_id, 'meeting': meeting, 'meeting_duration': meeting_duration, 'task_list_headings': task_list_headings, 'completed_task_list': completed_task_list, 'incomplete_task_list': incomplete_task_list, 'main_items': main_items, 'preliminary_items': preliminary_items, 'report_items': report_items, 'final_items': final_items, 'participants': participants, 'account': account}, RequestContext(request))


def agenda_print(request, meeting_id):
    if not request.user.is_authenticated():
        return HttpResponseRedirect(reverse('index'))
    meeting = Meeting.objects.get(pk=int(meeting_id))
    if meeting.owner != request.user:
        return HttpResponseRedirect(reverse('index'))
    response = create_pdf_agenda(request, meeting_id, 'screen')
    return response


def agenda_sent(request, meeting_id):
    return HttpResponse('Email successfully sent')


def minutes_list(request):
	if not request.user.is_authenticated():
		return HttpResponseRedirect(reverse('index'))
	minutes = Meeting.objects.filter(owner=request.user, agenda_locked=True)
	page_heading = 'Minutes'
	table_headings = ('Meeting number', 'Date', 'Location',)
	return render_to_response('minutes_list.html', {'user': request.user, 'minutes': minutes, 'page_heading': page_heading, 'table_headings': table_headings}, RequestContext(request))


def minutes_edit(request, meeting_id):
	if not request.user.is_authenticated():
		return HttpResponseRedirect(reverse('index'))
	page_heading = 'Create minutes'
	task_list_headings = ('Description', 'Assigned to', 'Deadline')
	meeting = Meeting.objects.get(pk=int(meeting_id))
	if meeting.owner != request.user:
		return HttpResponseRedirect(reverse('index'))
	meeting.agenda_locked = True
	meeting.save()
	AgendaItemFormSet = inlineformset_factory(Meeting, Item, extra=0, can_delete=True, widgets={'variety': HiddenInput(), 'background': Textarea(attrs={'rows': 3}), 'minute_notes': Textarea(attrs={'rows': 4}),})
	AgendaItemFormSet.form.base_fields['explainer'].queryset = Participant.objects.filter(owner=request.user)
	DecisionFormSet = inlineformset_factory(Meeting, Decision, extra=0, can_delete=True, widgets={'item': HiddenInput(), 'description': Textarea(attrs={'rows': 2}), 'owner': HiddenInput(),})
	TaskFormSet = inlineformset_factory(Meeting, Task, extra=0, can_delete=True, widgets={'item': HiddenInput(), 'status': HiddenInput(), 'owner': HiddenInput(), 'deadline': DateInput(attrs={'class': 'datepicker'}),})
	TaskFormSet.form.base_fields['participant'].queryset = Participant.objects.filter(owner=request.user)
	main_items = meeting.item_set.filter(owner=request.user, variety__exact='main')
	decision_items = meeting.decision_set.filter(owner=request.user)
	task_items = meeting.task_set.filter(owner=request.user)
	new_data_form = {}
	existing_data_forms = []
	existing_data_formset = {}
	decision_data_formset = {}
	task_data_formset = {}
	editable_section = 'none'
	incomplete_task_list = Task.objects.filter(owner=request.user, status="Incomplete")
	completed_task_list = Task.objects.filter(owner=request.user, status="Complete")
	account = Account.objects.filter(owner=request.user).last()
	
	def save_minutes_data(request, meeting):
		existing_data_formset = AgendaItemFormSet(request.POST, instance=meeting)
		if existing_data_formset.is_valid():
			for form in existing_data_formset:
				save_and_add_owner(request, form)
		decision_data_formset = DecisionFormSet(request.POST, instance=meeting)
		if decision_data_formset.is_valid():
			for form in decision_data_formset:
				save_and_add_owner(request, form)
		task_data_formset = TaskFormSet(request.POST, instance=meeting)
		if task_data_formset.is_valid():
			for form in task_data_formset:
				save_and_add_owner(request, form)
		
	if request.method == "POST":
	
		# Management of meeting details
		if 'edit_meeting_details_minutes_button' in request.POST:
			if request.POST['edit_meeting_details_minutes_button']=='edit_meeting_details':
				existing_data_forms = MeetingForm(instance=meeting)
				editable_section = 'is_meeting_details'
		if 'save_meeting_details_minutes_button' in request.POST:
			if request.POST['save_meeting_details_minutes_button']=='save_meeting_details':
				new_data_form = MeetingForm(request.POST, instance=meeting)
				if new_data_form.is_valid():
					new_data_form.save()
					editable_section = 'none'
		if 'cancel_meeting_details_minutes_button' in request.POST:
			if request.POST['cancel_meeting_details_minutes_button']=='cancel_meeting_details':
				editable_section = 'none'
				
		# Management of main items 
		if 'edit_main_items_agenda_button' in request.POST:
			if request.POST['edit_main_items_agenda_button']=='edit_main_items':
				existing_data_formset = AgendaItemFormSet(instance=meeting, queryset=main_items)
				decision_data_formset = DecisionFormSet(instance=meeting)
				task_data_formset = TaskFormSet(instance=meeting)
				editable_section = 'is_main_items'
		if 'save_main_items_agenda_button' in request.POST:
			if request.POST['save_main_items_agenda_button']=='save_main_items':
				save_minutes_data(request, meeting)
				editable_section = 'none'
		if 'add_decision_minutes_button' in request.POST:
			if 'add_decision_item_' in request.POST['add_decision_minutes_button']:
				save_minutes_data(request, meeting)
				item_number = str(request.POST['add_decision_minutes_button'])
				item_number = item_number[18:]
				new_decision = Decision(item_id=int(item_number), meeting_id=meeting_id, owner=request.user)
				new_decision.save()
				existing_data_formset = AgendaItemFormSet(instance=meeting, queryset=main_items)
				decision_data_formset = DecisionFormSet(instance=meeting)				
				task_data_formset = TaskFormSet(instance=meeting)				
				editable_section = 'is_main_items'
		if 'add_task_minutes_button' in request.POST:
			if 'add_task_item_' in request.POST['add_task_minutes_button']:
				save_minutes_data(request, meeting)
				item_number = str(request.POST['add_task_minutes_button'])
				item_number = item_number[14:]
				new_task = Task(item_id=int(item_number), meeting_id=meeting_id, owner=request.user, status = 'Incomplete')
				new_task.save()
				existing_data_formset = AgendaItemFormSet(instance=meeting, queryset=main_items)
				decision_data_formset = DecisionFormSet(instance=meeting)				
				task_data_formset = TaskFormSet(instance=meeting)				
				editable_section = 'is_main_items'	
						
	return render_to_response('minutes_edit.html', {'user': request.user, 'meeting_id': meeting_id, 'meeting': meeting, 'page_heading': page_heading, 'task_list_headings': task_list_headings, 'completed_task_list': completed_task_list, 'incomplete_task_list': incomplete_task_list,'editable_section': editable_section, 'main_items': main_items, 'decision_items': decision_items, 'task_items': task_items, 'existing_data_forms': existing_data_forms, 'existing_data_formset': existing_data_formset, 'new_data_form': new_data_form, 'decision_data_formset': decision_data_formset, 'task_data_formset': task_data_formset, 'account': account}, RequestContext(request))