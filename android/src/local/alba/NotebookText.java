package local.alba;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Rect;
import android.widget.EditText;

/** Rules follow actual text baselines, including font-size and scroll changes. */
final class NotebookText extends EditText {
    private String paper="plain";
    private final Paint rule=new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Rect line=new Rect();
    NotebookText(Context context){super(context);setTextSize(16);setIncludeFontPadding(false);}
    void setPaper(String value){paper=value;invalidate();}
    @Override protected void onDraw(Canvas canvas){
        if(paper.equals("ruled")||paper.equals("cornell")){
            float density=getResources().getDisplayMetrics().density;
            rule.setColor(0xffdfe4d7);rule.setStrokeWidth(Math.max(1,density*.6f));
            int count=getLineCount();float y=getPaddingTop(),step=getLineHeight();
            for(int i=0;i<count;i++){y=getLineBounds(i,line)+2*density;canvas.drawLine(getPaddingLeft(),y,getWidth()-getPaddingRight(),y,rule);}
            for(y+=step;y<Math.max(getHeight(),getScrollY()+getHeight())-getPaddingBottom();y+=step)
                canvas.drawLine(getPaddingLeft(),y,getWidth()-getPaddingRight(),y,rule);
        }
        super.onDraw(canvas);
    }
}
