import os, json, re
from datetime import datetime, date
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox, Querybox
from ttkbootstrap.tableview import Tableview
from tkcalendar import DateEntry

TASKS_FILE = 'tasks.json'
OWNERS_FILE = 'owners.json'
DATE_FORMAT_DISPLAY = '%d/%m/%Y'
DATE_FORMAT_ISO = '%Y-%m-%d'

def load_tasks():
    tasks = []
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        for t in raw:
            for field in ('start_date', 'due_date'):
                val = t.get(field, '')
                if re.match(r"^\d{4}-\d{2}-\d{2}$", val):
                    try:
                        dt = datetime.strptime(val, DATE_FORMAT_ISO)
                        t[field] = dt.strftime(DATE_FORMAT_DISPLAY)
                    except: pass
            tasks.append(t)
    return tasks

def save_tasks(tasks):
    out = []
    for t in tasks:
        copy = t.copy()
        for field in ('start_date', 'due_date'):
            val = copy.get(field, '')
            try:
                dt = datetime.strptime(val, DATE_FORMAT_DISPLAY)
                copy[field] = dt.strftime(DATE_FORMAT_DISPLAY)
            except: pass
        out.append(copy)
    with open(TASKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

def load_owners():
    if os.path.exists(OWNERS_FILE):
        with open(OWNERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_owners(owners):
    with open(OWNERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(owners, f, ensure_ascii=False, indent=2)

class TaskTrackerApp(tb.Window):
    def __init__(self):
        super().__init__(title="Weekly Task Tracker", themename="flatly", size=(1100, 700))
        self.resizable(True, True)
        self.tasks = load_tasks()
        self.owners = load_owners()
        self.edit_index = None
        self.build_ui()
        self.refresh_table()

    def build_ui(self):
        main = tb.Frame(self, padding=20)
        main.pack(fill=BOTH, expand=YES)

        # [Search/Filter]
        sf = tb.Frame(main)
        sf.pack(fill=X, pady=(0,8))
        tb.Label(sf, text='ค้นหา', bootstyle=SECONDARY).pack(side=LEFT)
        self.search_var = tb.StringVar()
        ent = tb.Entry(sf, textvariable=self.search_var, width=24)
        ent.pack(side=LEFT, padx=6)
        ent.bind('<KeyRelease>', lambda e: self.apply_filter())
        tb.Button(sf, text='ล้าง', bootstyle=(SECONDARY, OUTLINE), command=self.clear_filter).pack(side=LEFT, padx=8)
        tb.Label(sf, text='ผู้รับผิดชอบ', bootstyle=SECONDARY).pack(side=LEFT, padx=(24,0))
        self.filter_owner = tb.Combobox(sf, values=['All']+self.owners, state='readonly', width=15, bootstyle=INFO)
        self.filter_owner.set('All')
        self.filter_owner.pack(side=LEFT, padx=5)
        self.filter_owner.bind('<<ComboboxSelected>>', lambda e: self.apply_filter())
        tb.Label(sf, text='สถานะ', bootstyle=SECONDARY).pack(side=LEFT, padx=(24,0))
        self.filter_status = tb.Combobox(sf, values=['All','Pending','In Progress','Done'], state='readonly', width=15, bootstyle=INFO)
        self.filter_status.set('All')
        self.filter_status.pack(side=LEFT, padx=5)
        self.filter_status.bind('<<ComboboxSelected>>', lambda e: self.apply_filter())

        # [Info]
        info = tb.Labelframe(main, text='รายละเอียด', bootstyle=INFO)
        info.pack(fill=X, pady=8)
        self.var_project = tb.StringVar()
        self.var_detail = tb.StringVar()
        tb.Label(info, text='ชื่อโปรเจกต์').grid(row=0,column=0,padx=6, pady=8, sticky='e')
        tb.Entry(info, textvariable=self.var_project, width=26).grid(row=0,column=1, padx=6)
        tb.Label(info, text='รายละเอียด').grid(row=0,column=2,padx=6, sticky='e')
        tb.Entry(info, textvariable=self.var_detail, width=34).grid(row=0,column=3, padx=6)

        # [Dates & Status]
        ds = tb.Labelframe(main, text='วันที่ & สถานะ', bootstyle=INFO)
        ds.pack(fill=X, pady=8)
        today = date.today()
        self.var_start = tb.StringVar()
        self.var_due = tb.StringVar()
        self.var_status = tb.StringVar()
        tb.Label(ds, text='วันที่เริ่ม').grid(row=0,column=0,padx=6, pady=8)
        DateEntry(ds, textvariable=self.var_start, date_pattern='dd/MM/yyyy', mindate=today).grid(row=0,column=1, padx=6)

        tb.Label(ds, text='วันที่ครบกำหนด').grid(row=0,column=2,padx=6)
        DateEntry(ds, textvariable=self.var_due, date_pattern='dd/MM/yyyy', mindate=today).grid(row=0,column=3, padx=6)


        tb.Label(ds, text='สถานะ').grid(row=0,column=4,padx=6)
        tb.Combobox(ds, textvariable=self.var_status, values=['Pending','In Progress','Done'], state='readonly', width=14, bootstyle=INFO).grid(row=0,column=5, padx=6)
        self.var_status.set('Pending')

        # [Owners]
        ow = tb.Labelframe(main, text='ผู้รับผิดชอบ', bootstyle=INFO)
        ow.pack(fill=X, pady=8)
        self.owner_cb = tb.Combobox(ow, values=self.owners, width=21, bootstyle=INFO)
        self.owner_cb.set('เลือกผู้รับผิดชอบ')
        self.owner_cb.grid(row=0,column=0,padx=6, pady=5)
        tb.Button(ow, text='+', bootstyle=SUCCESS, width=3, command=self.add_owner).grid(row=0,column=1)
        tb.Button(ow, text='-', bootstyle=DANGER, width=3, command=self.delete_owner).grid(row=0,column=2)
        tb.Button(ow, text='เพิ่มในรายการ', bootstyle=(PRIMARY, OUTLINE), command=self.add_selected_owner).grid(row=0,column=3, padx=6)
        self.sel_list = tb.Listbox(ow, height=4, font=('Segoe UI', 11), selectbackground="#CEE7F5")
        self.sel_list.grid(row=1,column=0,columnspan=4, sticky='ew', padx=6, pady=4)

        # [Action Button]
        action = tb.Frame(main)
        action.pack(fill=X, pady=12)
        tb.Button(action, text='➕ เพิ่มงาน', bootstyle=SUCCESS, command=self.add_task, width=16).pack(side=LEFT, padx=7)
        tb.Button(action, text='ยกเลิก', bootstyle=WARNING, command=self.cancel_edit, width=10).pack(side=LEFT, padx=7)
        tb.Button(action, text='🗑️ ลบ', bootstyle=DANGER, command=self.delete_task, width=10).pack(side=LEFT, padx=7)

        # [Task Table]
        tf = tb.Frame(main, relief='flat')
        tf.pack(fill=BOTH, expand=YES, pady=(10,0))
        cols = ['Project','Detail','Start','Due','Owners','Status']
        self.table = tb.Treeview(tf, columns=cols, show='headings', bootstyle=INFO, height=15)
        for c in cols:
            self.table.heading(c, text=c)
            self.table.column(c, width=170, anchor='center')
        vsb = tb.Scrollbar(tf, orient='vertical', command=self.table.yview, bootstyle=INFO)
        self.table.configure(yscroll=vsb.set)
        vsb.pack(side=RIGHT, fill=Y)
        self.table.pack(fill=BOTH, expand=YES)
        self.table.bind('<Double-1>', self.on_double_click)
        self.table.bind('<Button-3>', self.show_context_menu)
        self.menu = tb.Menu(self, tearoff=0)
        self.menu.add_command(label='Edit', command=lambda: self.on_double_click(None))
        self.menu.add_command(label='Delete', command=self.delete_task)

    # ---------- (Function เหมือนเดิม)
    def show_context_menu(self, event):
        row_id = self.table.identify_row(event.y)
        if row_id:
            self.table.selection_set(row_id)
            self.menu.tk_popup(event.x_root, event.y_root)
    def add_owner(self):
        name = Querybox.get_string('New Owner', 'Enter owner name:', parent=self)
        if name and name not in self.owners:
            self.owners.append(name)
            save_owners(self.owners)
            self.owner_cb['values'] = self.owners
            self.owner_cb.set(name)
    def delete_owner(self):
        name = self.owner_cb.get()
        if name in self.owners and Messagebox.yesno(f'Delete owner "{name}"?', title="Confirm", parent=self):
            self.owners.remove(name)
            save_owners(self.owners)
            self.owner_cb['values'] = self.owners
            self.owner_cb.set('เลือกผู้รับผิดชอบ')
            for idx, val in enumerate(self.sel_list.get(0, 'end')):
                if val == name:
                    self.sel_list.delete(idx)
                    break
    def add_selected_owner(self):
        name = self.owner_cb.get()
        if name and name not in self.sel_list.get(0, 'end'):
            self.sel_list.insert('end', name)
    def add_task(self):
        proj = self.var_project.get().strip()
        det = self.var_detail.get().strip()
        start = self.var_start.get()
        due = self.var_due.get()
        status = self.var_status.get()
        owners = list(self.sel_list.get(0, 'end'))
        if not proj or not owners:
            Messagebox.show_error('โปรดระบุชื่อโครงการและผู้รับผิดชอบ', title="Error", parent=self)
            return
        try:
            datetime.strptime(start, DATE_FORMAT_DISPLAY)
            datetime.strptime(due, DATE_FORMAT_DISPLAY).date()
        except:
            Messagebox.show_error('รูปแบบวันที่ไม่ถูกต้อง', title="Error", parent=self)
            return
        record = {'project':proj, 'detail':det, 'start_date':start, 'due_date':due, 'owners':owners, 'status':status}
        if self.edit_index is None:
            self.tasks.append(record)
        else:
            self.tasks[self.edit_index] = record
        save_tasks(self.tasks)
        self.refresh_table()
        self.cancel_edit()
    def on_double_click(self, event):
        sel = self.table.selection()
        if not sel: return
        idx = int(sel[0])
        t = self.tasks[idx]
        self.var_project.set(t['project'])
        self.var_detail.set(t['detail'])
        self.var_start.set(t['start_date'])
        self.var_due.set(t['due_date'])
        self.var_status.set(t['status'])
        self.sel_list.delete(0, 'end')
        for o in t['owners']:
            self.sel_list.insert('end', o)
        self.edit_index = idx
    def cancel_edit(self):
        self.var_project.set('')
        self.var_detail.set('')
        self.var_start.set('')
        self.var_due.set('')
        self.var_status.set('Pending')
        self.sel_list.delete(0, 'end')
        self.edit_index = None
        save_tasks(self.tasks)
    def delete_task(self):
        sel = self.table.selection()
        if not sel: return
        idx = int(sel[0])
        if Messagebox.yesno('ลบงานนี้หรือไม่?', title="Confirm", parent=self):
            self.tasks.pop(idx)
            save_tasks(self.tasks)
            self.refresh_table()
    def refresh_table(self, items=None):
        for i in self.table.get_children():
            self.table.delete(i)
        data = items if items is not None else self.tasks
        for i, t in enumerate(data):
            due = datetime.strptime(t['due_date'], DATE_FORMAT_DISPLAY).date()
            delta = (due - date.today()).days
            tag = ''
            if delta <= 2: tag='danger'
            elif delta <=5: tag='warning'
            values = (t['project'], t['detail'], t['start_date'], t['due_date'], ', '.join(t['owners']), t['status'])
            self.table.insert('', 'end', iid=str(i), values=values, tags=(tag,))
        self.table.tag_configure('danger', background='#FFD6D6')
        self.table.tag_configure('warning', background='#FFF7CF')
    def apply_filter(self):
        key = self.search_var.get().lower()
        owner = self.filter_owner.get()
        status = self.filter_status.get()
        filtered = []
        for t in self.tasks:
            if key and key not in t['project'].lower() and key not in t['detail'].lower(): continue
            if owner != 'All' and owner not in t['owners']: continue
            if status != 'All' and t['status'] != status: continue
            filtered.append(t)
        self.refresh_table(filtered)
    def clear_filter(self):
        self.search_var.set('')
        self.filter_owner.set('All')
        self.filter_status.set('All')
        self.refresh_table()

if __name__ == '__main__':
    TaskTrackerApp().mainloop()
