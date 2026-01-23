/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { Component, onWillStart } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
export class ActivityDashboard extends Component {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.metrics = {
            total: 0,
            overdue: 0,
            today: 0,
            planned: 0,
            done: 0,
            activityTypes: 0,
        };
        this.chartData = {
            byUser: [],
            overTime: [],
            byType: [],
            statusMix: [],
            linePath: "",
        };
        this.planned_activity = [];
        this.today_activity = [];
        this.overdue_activity = [];
        this.done_activity = [];
        onWillStart(async () => await this.render_dashboards());
    }
    async render_dashboards() {
        const today = new Date();
        const startDate = new Date();
        startDate.setDate(today.getDate() - 29);
        const dateString = (dt) => dt.toISOString().slice(0, 10);
        const activeCtx = { context: { active_test: false } };
        const bucketData = await this.orm.call(
            'mail.activity',
            'get_dashboard_buckets',
            [],
            {},
        );
        const [
            stateGroups,
            userGroups,
            dateGroups,
            typeGroups,
            totalCount,
        ] = await Promise.all([
            this.orm.call(
                'mail.activity',
                'read_group',
                [
                    [],
                    ['state'],
                    ['state'],
                ],
                activeCtx,
            ),
            this.orm.call(
                'mail.activity',
                'read_group',
                [
                    [],
                    ['user_id'],
                    ['user_id'],
                ],
                activeCtx,
            ),
            this.orm.call(
                'mail.activity',
                'read_group',
                [
                    [
                        '&',
                        ['date_deadline', '!=', false],
                        ['date_deadline', '>=', dateString(startDate)],
                    ],
                    ['date_deadline'],
                    ['date_deadline'],
                ],
                activeCtx,
            ),
            this.orm.call(
                'mail.activity',
                'read_group',
                [
                    [],
                    ['activity_type_id'],
                    ['activity_type_id'],
                ],
                activeCtx,
            ),
            this.orm.call(
                'mail.activity',
                'search_count',
                [
                    [['id', '!=', 0]],
                ],
                activeCtx,
            ),
        ]);
        const plannedFull = bucketData?.planned || [];
        const todayFull = bucketData?.today || [];
        const overdueFull = bucketData?.overdue || [];
        const doneFull = bucketData?.done || [];
        const planned_activity = plannedFull.slice(0, 10);
        const today_activity = todayFull.slice(0, 10);
        const overdue_activity = overdueFull.slice(0, 10);
        const done_activity = doneFull.slice(0, 10);
        const stateCount = this._stateToCount(stateGroups || []);
        if (!stateCount.planned && !stateCount.today && !stateCount.overdue && !stateCount.done) {
            stateCount.planned = plannedFull.length;
            stateCount.today = todayFull.length;
            stateCount.overdue = overdueFull.length;
            stateCount.done = doneFull.length;
        }
        this.metrics = {
            total: totalCount || plannedFull.length + todayFull.length + overdueFull.length + doneFull.length,
            overdue: stateCount.overdue || 0,
            today: stateCount.today || 0,
            planned: stateCount.planned || 0,
            done: stateCount.done || 0,
            activityTypes: (typeGroups || []).filter((g) => g.activity_type_id).length
                || new Set([...plannedFull, ...todayFull, ...overdueFull, ...doneFull]
                    .map((rec) => rec.activity_type_id && rec.activity_type_id[0])
                    .filter(Boolean)).size,
        };
        this.chartData = this._buildCharts({
            userGroups: userGroups || [],
            dateGroups: dateGroups || [],
            typeGroups: typeGroups || [],
            stateCount,
            records: [...plannedFull, ...todayFull, ...overdueFull, ...doneFull],
        });
        this.done_activity = done_activity;
        this.planned_activity = planned_activity;
        this.today_activity = today_activity;
        this.overdue_activity = overdue_activity;
    }
    _stateToCount(groups) {
        const count = {};
        for (const group of groups) {
            const key = group.state || group.state === false ? group.state : null;
            if (key) {
                count[key] = group.__count;
            }
        }
        return count;
    }
    _buildCharts({ userGroups, dateGroups, typeGroups, stateCount, records }) {
        let byUser = userGroups.map((group) => ({
            label: group.user_id ? group.user_id[1] : _t("Unassigned"),
            value: group.__count || 0,
        })).filter((item) => item.value > 0);
        if (!byUser.length && records?.length) {
            const map = {};
            for (const rec of records) {
                const label = rec.user_id ? rec.user_id[1] : _t("Unassigned");
                map[label] = (map[label] || 0) + 1;
            }
            byUser = Object.entries(map).map(([label, value]) => ({ label, value }));
        }
        const maxUser = byUser.length ? Math.max(...byUser.map((item) => item.value)) : 0;
        const sortedDateGroups = [...dateGroups].filter((d) => d.date_deadline)
            .sort((a, b) => a.date_deadline.localeCompare(b.date_deadline));
        let overTime = sortedDateGroups.map((group) => ({
            label: group.date_deadline,
            value: group.__count || 0,
        }));
        if (!overTime.length && records?.length) {
            const map = {};
            for (const rec of records) {
                if (!rec.date_deadline) {
                    continue;
                }
                map[rec.date_deadline] = (map[rec.date_deadline] || 0) + 1;
            }
            overTime = Object.entries(map)
                .sort((a, b) => a[0].localeCompare(b[0]))
                .map(([label, value]) => ({ label, value }));
        }
        const maxOverTime = overTime.length ? Math.max(...overTime.map((item) => item.value)) : 0;
        let byType = typeGroups.map((group) => ({
            label: group.activity_type_id ? group.activity_type_id[1] : _t("Unspecified"),
            value: group.__count || 0,
        })).filter((item) => item.value > 0);
        if (!byType.length && records?.length) {
            const map = {};
            for (const rec of records) {
                const label = rec.activity_type_id ? rec.activity_type_id[1] : _t("Unspecified");
                map[label] = (map[label] || 0) + 1;
            }
            byType = Object.entries(map).map(([label, value]) => ({ label, value }));
        }
        const maxStatus = Math.max(
            stateCount.planned || 0,
            stateCount.today || 0,
            stateCount.overdue || 0,
            stateCount.done || 0,
        );
        const statusMix = [
            { label: _t("Planned"), value: stateCount.planned || 0, key: "planned" },
            { label: _t("Today"), value: stateCount.today || 0, key: "today" },
            { label: _t("Overdue"), value: stateCount.overdue || 0, key: "overdue" },
            { label: _t("Completed"), value: stateCount.done || 0, key: "done" },
        ];
        const linePath = this._buildLinePath(overTime);
        const donutSegments = this._buildDonutSegments(byType);
        return {
            byUser,
            byUserMax: maxUser,
            overTime,
            overTimeMax: maxOverTime,
            byType: donutSegments,
            statusMix,
            statusMax: maxStatus || 1,
            linePath,
        };
    }
    _buildLinePath(series) {
        if (!series.length) {
            return "";
        }
        const maxVal = Math.max(...series.map((s) => s.value), 1);
        const stepX = series.length > 1 ? 100 / (series.length - 1) : 100;
        return series.map((point, idx) => {
            const x = (idx * stepX).toFixed(2);
            const y = (100 - (point.value / maxVal) * 100).toFixed(2);
            return `${x},${y}`;
        }).join(" ");
    }
    _buildDonutSegments(series) {
        const total = series.reduce((acc, item) => acc + item.value, 0) || 1;
        let offset = 25;
        const palette = ["#5B8DEF", "#3CC3A3", "#FFB347", "#F25F5C", "#A29BFE", "#7f8c8d"];
        return series.map((item, idx) => {
            const pct = (item.value / total) * 100;
            const segment = {
                label: item.label,
                value: item.value,
                pct: pct.toFixed(2),
                offset: (-offset).toFixed(2),
                color: palette[idx % palette.length],
            };
            offset += pct;
            return segment;
        });
    }
    _statusColor(key) {
        const colors = {
            planned: "#2d9cdb",
            today: "#f2c94c",
            overdue: "#eb5757",
            done: "#95a5a6",
        };
        return colors[key] || "#7f8c8d";
    }
   /**
     * Event handler to open the list of all activities.
     */
	show_all_activities(e) {
		e.stopPropagation();
		e.preventDefault();
		const options = {
            on_reverse_breadcrumb: this.on_reverse_breadcrumb,
        };
		this.actionService.doAction({
        name: _t("All Activities"),
        type: 'ir.actions.act_window',
        res_model: 'mail.activity',
        view_mode: 'list,form',
        domain: [['active', 'in', [true,false]]],
        views: [[false, 'list'], [false, 'form']],
        target: 'current'
        }, options);
	}
	/**
     * Event handler to open the list of planned activities.
     */
	show_planned_activities(e) {
		e.stopPropagation();
		e.preventDefault();
		const options = {
            on_reverse_breadcrumb: this.on_reverse_breadcrumb,
        };
		this.actionService.doAction({
        name: _t("Planned Activities"),
        type: 'ir.actions.act_window',
        res_model: 'mail.activity',
        domain: [['state', '=', 'planned']],
        view_mode: 'list,form',
        views: [[false, 'list'], [false, 'form']],
        target: 'current'
        }, options);
	}
	/**
     * Event handler to open the list of completed activities.
     */
	show_completed_activities(e) {
		e.stopPropagation();
		e.preventDefault();
		const options = {
            on_reverse_breadcrumb: this.on_reverse_breadcrumb,
        };
		this.actionService.doAction({
        name: _t("Completed Activities"),
        type: 'ir.actions.act_window',
        res_model: 'mail.activity',
        domain: [['state', '=', 'done'],['active','in',[true,false]]],
        view_mode: 'list,form',
        views: [[false, 'list'], [false, 'form']],
        target: 'current'
        }, options);
	}
	/**
     * Event handler to open the list of today's activities.
     */
	show_today_activities(e) {
		e.stopPropagation();
		e.preventDefault();
		const options = {
            on_reverse_breadcrumb: this.on_reverse_breadcrumb,
        };
		this.actionService.doAction({
        name: _t("Today's Activities"),
        type: 'ir.actions.act_window',
        res_model: 'mail.activity',
        domain: [['state', '=', 'today']],
        view_mode: 'list,form',
        views: [[false, 'list'], [false, 'form']],
        target: 'current'
        }, options);
	}
	/**
     * Event handler to open the list of overdue activities.
     */
	show_overdue_activities(e) {
		e.stopPropagation();
		e.preventDefault();
		const options = {
            on_reverse_breadcrumb: this.on_reverse_breadcrumb,
        };
		this.actionService.doAction({
        name: _t("Overdue Activities"),
        type: 'ir.actions.act_window',
        res_model: 'mail.activity',
        domain: [['state', '=', 'overdue']],
        view_mode: 'list,form',
        views: [[false, 'list'], [false, 'form']],
        target: 'current'
        }, options);
	}
	/**
     * Event handler to open the list of activity types.
     */
	show_activity_types(e) {
		e.stopPropagation();
		e.preventDefault();
		const options = {
            on_reverse_breadcrumb: this.on_reverse_breadcrumb,
        };
		this.actionService.doAction({
        name: _t("Activity Type"),
        type: 'ir.actions.act_window',
        res_model: 'mail.activity.type',
        view_mode: 'list,form',
        views: [[false, 'list'], [false, 'form']],
        target: 'current'
        }, options);
	}
    /**
     * Event handler for view button click.
     */
	click_view(e) {
	     var id = e.target.value;
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            name: 'All Activity',
            res_model: 'mail.activity',
            res_id: parseInt(id),
            views: [[false, 'form']],
            view_mode: 'form',
            target: 'current'
        });
	}
	  /**
     * Event handler for view button click.
     */
	async click_origin(e) {
        const activityId = parseInt(e.currentTarget?.value, 10)
        if (!Number.isInteger(activityId)) {
            this.notification.add(
                _t("Activity reference is missing."),
                { type: "warning" }
            );
            return;
        }
        const result = await this.orm.call(
            'mail.activity',
            'get_activity',
            [activityId],
            {}
        )
        if (!result || !result.model || !result.res_id) {
            this.notification.add(
                _t("Access restricted or record missing."),
                { type: "warning" }
            );
            return;
        }
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            name: 'Activity Origin',
            res_model: result.model,
            res_id: result.res_id,
            views: [[false, 'form']],
            view_mode: 'form',
            target: 'current'
        });
	}
}
ActivityDashboard.template = "ActivityDashboard";
ActivityDashboard.components = { Layout };
registry.category("actions").add("activity_dashboard", ActivityDashboard);
