define(["jquery", "widgets/js/widget"], function($, widget) {

    var SVGView = widget.DOMWidgetView.extend({

        render: function(){
            this.$svg = $('<svg>');
            this.$el.append(this.$svg);
            this.svg_changed();
            this.$el.attr({overflow: 'hidden'});
            this.model.on('change:svg', this.svg_changed, this);

        },

        svg_changed: function() {
            this.$svg.html(this.model.get('svg'))
        },
    });

    var ElementView = widget.DOMWidgetView.extend({

        render: function() {
            
        }
    })

    return {SVGView: SVGView};
});



for (var i=0; i<this.model.sync_names.length; i++) {
                
            }