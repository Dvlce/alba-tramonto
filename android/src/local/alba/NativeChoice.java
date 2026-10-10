package local.alba;

import android.content.Context;
import android.graphics.Canvas;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.LinearLayout;
import android.widget.Spinner;
import android.widget.TextView;

/** Compact readable native selectors used by settings and Notte tools. */
final class NativeChoice extends Spinner {
    NativeChoice(Context context){
        super(context,Spinner.MODE_DROPDOWN);setWillNotDraw(false);NativeUi ui=new NativeUi(context);setMinimumHeight(NativeUi.dp(context,48));
        setBackground(NativeUi.shape(context,ui.surface,16,ui.line));setPopupBackgroundDrawable(NativeUi.shape(context,ui.surface,16,ui.line));
        setPadding(NativeUi.dp(context,2),0,NativeUi.dp(context,30),0);LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=NativeUi.dp(context,12);setLayoutParams(p);
    }
    @Override protected void onDraw(Canvas canvas){super.onDraw(canvas);int size=NativeUi.dp(getContext(),16),right=getWidth()-NativeUi.dp(getContext(),12);NativeIcon arrow=new NativeIcon(getContext(),"down",new NativeUi(getContext()).muted,16);arrow.setBounds(right-size,(getHeight()-size)/2,right,(getHeight()+size)/2);arrow.draw(canvas);}
    static ArrayAdapter<String> options(Context context,String[] values){return new ArrayAdapter<String>(context,android.R.layout.simple_spinner_dropdown_item,values){
        @Override public View getView(int position,View view,ViewGroup parent){return row(position,false);}
        @Override public View getDropDownView(int position,View view,ViewGroup parent){return row(position,true);}
        private TextView row(int position,boolean dropdown){TextView value=new TextView(context);value.setText(getItem(position));NativeUi.text(value,14,false);value.setGravity(android.view.Gravity.CENTER_VERTICAL);value.setPadding(NativeUi.dp(context,14),NativeUi.dp(context,10),NativeUi.dp(context,14),NativeUi.dp(context,10));value.setMinimumHeight(NativeUi.dp(context,48));if(dropdown)value.setBackground(NativeUi.touch(context,new NativeUi(context).surface,12,0));return value;}
    };}
}
